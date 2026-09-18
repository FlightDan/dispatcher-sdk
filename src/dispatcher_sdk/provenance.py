"""Authenticated cross-Run provenance and conservative permanent disposal.

The registry is explicit: it does not discover arbitrary application files or
references.  A caller must register every Run and declare the registry scope
closed before a disposal plan can be applicable.  Permanent disposal is
currently limited to terminal, task-free Runs with no delivery, recovery,
subscription, link, Kernel, or externally registered journal obligations.
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

from .content import ContentIntegrityError, decode_value
from .maintenance import Lease
from .storage_connection import connect as storage_connect


_REGISTRY_SCHEMA = """
CREATE TABLE provenance_registry (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 document TEXT NOT NULL,
 authentication TEXT NOT NULL
)
"""
_RUN_TERMINAL = {"succeeded", "failed", "cancelled"}
_HEX_DIGEST = set("0123456789abcdef")
_Failpoint = Callable[[str], None]


def _registry_schema_objects(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE tbl_name='provenance_registry' ORDER BY type,name"
        )
    ]


def _reference_registry_schema() -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(_REGISTRY_SCHEMA)
        return _registry_schema_objects(connection)


class ProvenanceError(RuntimeError):
    """Provenance cannot be authenticated or an operation is unsafe."""


class RegistryIntegrityError(ProvenanceError):
    """The registry document or an authenticated locator was corrupted."""


class DisposalBlocked(ProvenanceError):
    """A disposal plan has blockers and cannot be applied."""


class StaleDisposalPlan(ProvenanceError):
    """The source or registry changed after disposal was planned."""


def _canonical(value: Any) -> str:
    def validate(item: Any) -> None:
        if item is None or type(item) in {bool, str, int, float}:
            return
        if type(item) is list:
            for child in item:
                validate(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                validate(child)
            return
        raise ValueError("value must be strict JSON with string object keys")

    validate(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _valid_digest(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and set(value) <= _HEX_DIGEST


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def _validate_source_schema(connection: sqlite3.Connection) -> None:
    """Require the exact current Orchestrator tables, indexes, and triggers."""
    try:
        # Import lazily so provenance remains safe to import while the
        # orchestrator package itself is initializing.
        from .orchestrator.engine import Orchestrator

        if not Orchestrator.__new__(Orchestrator)._validate_existing_store(connection):
            raise ProvenanceError("source is not an initialized Orchestrator store")
    except ProvenanceError:
        raise
    except (ValueError, RuntimeError, sqlite3.DatabaseError) as exc:
        raise ProvenanceError(
            "source does not match the exact current Orchestrator schema and triggers"
        ) from exc


class ProvenanceRegistry:
    """A serialized HMAC-authenticated registry stored in its own SQLite file."""

    def __init__(self, path: str | os.PathLike[str], signing_key: bytes):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("signing_key must contain at least 32 bytes")
        self.path = Path(path).expanduser().absolute()
        self._key = bytes(signing_key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            objects = _registry_schema_objects(connection)
            if not objects:
                connection.execute(_REGISTRY_SCHEMA)
                document = {
                    "format_version": 1,
                    "revision": 0,
                    "scope_closed": False,
                    "runs": {},
                    "references": [],
                }
                encoded = _canonical(document)
                connection.execute(
                    "INSERT INTO provenance_registry VALUES(1,?,?)",
                    (encoded, self._authenticate_text(encoded)),
                )
            elif objects != _reference_registry_schema():
                raise RegistryIntegrityError("provenance registry schema is unsupported or corrupt")
            self._load_document(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _authenticate_text(self, encoded: str) -> str:
        return hmac.new(self._key, encoded.encode("utf-8"), hashlib.sha256).hexdigest()

    def authenticate(self, value: Any) -> str:
        """Return the registry-key HMAC for a strict canonical JSON value."""
        return self._authenticate_text(_canonical(value))

    def _connect(self) -> sqlite3.Connection:
        connection = storage_connect(self.path, timeout=30)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous=FULL")
            return connection
        except BaseException:
            connection.close()
            raise

    def _load_document(self, connection: sqlite3.Connection) -> dict[str, Any]:
        rows = connection.execute(
            "SELECT document,authentication FROM provenance_registry WHERE singleton=1"
        ).fetchall()
        if len(rows) != 1 or type(rows[0][0]) is not str or type(rows[0][1]) is not str:
            raise RegistryIntegrityError("provenance registry metadata is missing or malformed")
        encoded, authentication = rows[0][0], rows[0][1]
        if not hmac.compare_digest(authentication, self._authenticate_text(encoded)):
            raise RegistryIntegrityError("provenance registry authentication failed")
        try:
            document = json.loads(encoded)
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise RegistryIntegrityError("provenance registry document is invalid JSON") from exc
        if _canonical(document) != encoded:
            raise RegistryIntegrityError("provenance registry document is not canonical")
        if (
            type(document) is not dict
            or set(document) != {
                "format_version", "revision", "scope_closed", "runs", "references"
            }
            or document["format_version"] != 1
            or type(document["revision"]) is not int
            or document["revision"] < 0
            or type(document["scope_closed"]) is not bool
            or type(document["runs"]) is not dict
            or type(document["references"]) is not list
        ):
            raise RegistryIntegrityError("provenance registry document has an invalid shape")
        for origin, record in document["runs"].items():
            if not _valid_digest(origin) or type(record) is not dict:
                raise RegistryIntegrityError("provenance registry contains an invalid Run record")
            if record.get("origin_digest") != origin or record.get("state") not in {
                "active", "archived", "deleting", "disposed"
            }:
                raise RegistryIntegrityError("provenance registry Run identity is invalid")
        for reference in document["references"]:
            if (
                type(reference) is not dict
                or set(reference) != {"source", "target", "expected_origin_digest"}
                or not _valid_digest(reference["source"])
                or not _valid_digest(reference["target"])
                or reference["target"] != reference["expected_origin_digest"]
            ):
                raise RegistryIntegrityError("provenance registry contains an invalid reference")
        return document

    def _store_document(self, connection: sqlite3.Connection, document: dict[str, Any]) -> None:
        document["revision"] += 1
        encoded = _canonical(document)
        cursor = connection.execute(
            "UPDATE provenance_registry SET document=?,authentication=? WHERE singleton=1",
            (encoded, self._authenticate_text(encoded)),
        )
        if cursor.rowcount != 1:
            raise RegistryIntegrityError("provenance registry row disappeared")

    def _snapshot(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            document = self._load_document(connection)
            connection.rollback()
            return document

    @property
    def revision(self) -> int:
        return self._snapshot()["revision"]

    def close_scope(self) -> int:
        """Record the caller's assertion that all external provenance is registered."""
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                document = self._load_document(connection)
                if not document["scope_closed"]:
                    document["scope_closed"] = True
                    self._store_document(connection, document)
                connection.commit()
                return document["revision"]
            except BaseException:
                connection.rollback()
                raise

    def register_run(
        self,
        source_db: str | os.PathLike[str],
        run_id: str,
        *,
        header: Any | None = None,
    ) -> str:
        """Register one hot Run using its stable store identity and explicit header."""
        if type(run_id) is not str or not run_id:
            raise ValueError("run_id must be a nonempty string")
        source = Path(source_db).expanduser().resolve(strict=True)
        header = {} if header is None else header
        _canonical(header)
        with closing(_read_only(source)) as store:
            store.execute("BEGIN")
            identity = store.execute(
                "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
            ).fetchone()
            if identity is None:
                raise ProvenanceError("source has no stable storage identity")
            if store.execute(
                "SELECT 1 FROM sdk_disposed_runs WHERE run_id=?", (run_id,)
            ).fetchone():
                raise ProvenanceError("a disposed Run identity cannot be registered again")
            if store.execute("SELECT 1 FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone() is None:
                raise ProvenanceError("source Run does not exist")
        identity_document = {
            "domain": "dispatcher-sdk-run-origin-v1",
            "store_id": identity[0],
            "incarnation": identity[1],
            "run_id": run_id,
            "header": header,
        }
        origin = _digest(identity_document)
        record = {
            **identity_document,
            "origin_digest": origin,
            "state": "active",
            "hot_path": str(source),
            "cold_locator": None,
            "deletion": None,
            "tombstone": None,
        }
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                document = self._load_document(connection)
                for existing_origin, existing in document["runs"].items():
                    same_identity = (
                        existing.get("store_id"), existing.get("incarnation"), existing.get("run_id")
                    ) == (identity[0], identity[1], run_id)
                    if same_identity and existing_origin != origin:
                        raise ProvenanceError("Run identity is already registered with another header")
                existing = document["runs"].get(origin)
                if existing is not None:
                    if existing["state"] in {"deleting", "disposed"}:
                        raise ProvenanceError("Run identity is deleting or permanently disposed")
                    if existing != record:
                        raise ProvenanceError("Run origin registration conflicts with existing metadata")
                else:
                    document["runs"][origin] = record
                    self._store_document(connection, document)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return origin

    def add_reference(
        self, source: str, target: str, expected_origin_digest: str
    ) -> int:
        """Add one authenticated edge after verifying the target's exact origin digest."""
        if not all(_valid_digest(value) for value in (source, target, expected_origin_digest)):
            raise ValueError("reference identities must be lowercase SHA-256 digests")
        if target != expected_origin_digest:
            raise ProvenanceError("target origin digest does not match the expected digest")
        reference = {
            "source": source,
            "target": target,
            "expected_origin_digest": expected_origin_digest,
        }
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                document = self._load_document(connection)
                source_record = document["runs"].get(source)
                target_record = document["runs"].get(target)
                if source_record is None or target_record is None:
                    raise ProvenanceError("both reference endpoints must be registered")
                if source_record["state"] in {"deleting", "disposed"}:
                    raise ProvenanceError("reference source is deleting or disposed")
                if target_record["state"] in {"deleting", "disposed"}:
                    raise ProvenanceError("reference target is deleting or disposed")
                if reference not in document["references"]:
                    document["references"].append(reference)
                    document["references"].sort(
                        key=lambda item: (item["source"], item["target"])
                    )
                    self._store_document(connection, document)
                connection.commit()
                return document["revision"]
            except BaseException:
                connection.rollback()
                raise

    def register_archive(
        self,
        origin_digest: str,
        locator: str | os.PathLike[str],
        *,
        artifact_digest: str,
    ) -> int:
        """Register a supplemental, byte-verified local archive artifact.

        Remote locator verification is intentionally unsupported in this first
        implementation.  A generic file digest does not prove that the file
        contains this Run origin, so the authoritative hot locator is retained
        and disposal never relies on this archive registration.
        """
        if not _valid_digest(origin_digest) or not _valid_digest(artifact_digest):
            raise ValueError("origin and artifact digests must be lowercase SHA-256 digests")
        artifact = Path(locator).expanduser().resolve(strict=True)
        if not artifact.is_file():
            raise ProvenanceError("archive locator must identify a regular local file")
        actual = _file_digest(artifact)
        if actual != artifact_digest:
            raise ProvenanceError("archive artifact digest does not match")
        locator_record = {
            "kind": "cold",
            "path": str(artifact),
            "artifact_digest": actual,
            "origin_digest": origin_digest,
            "origin_bound": False,
        }
        locator_record["authentication"] = self.authenticate(locator_record)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                document = self._load_document(connection)
                record = document["runs"].get(origin_digest)
                if record is None:
                    raise ProvenanceError("archive origin is not registered")
                if record["state"] in {"deleting", "disposed"}:
                    raise ProvenanceError("archive origin is deleting or disposed")
                record["cold_locator"] = locator_record
                self._store_document(connection, document)
                connection.commit()
                return document["revision"]
            except BaseException:
                connection.rollback()
                raise

    def verify_locator(self, locator: dict[str, Any]) -> bool:
        if type(locator) is not dict or type(locator.get("authentication")) is not str:
            raise RegistryIntegrityError("locator authentication is missing")
        unsigned = dict(locator)
        authentication = unsigned.pop("authentication")
        if not hmac.compare_digest(authentication, self.authenticate(unsigned)):
            raise RegistryIntegrityError("locator authentication failed")
        return True

    def _verify_cold_locator(self, locator: dict[str, Any]) -> None:
        self.verify_locator(locator)
        if locator.get("kind") != "cold" or locator.get("origin_bound") is not False:
            raise RegistryIntegrityError("cold locator has an unsupported origin contract")
        try:
            artifact = Path(locator["path"]).resolve(strict=True)
        except (KeyError, OSError) as exc:
            raise RegistryIntegrityError("cold archive artifact is missing") from exc
        if not artifact.is_file() or _file_digest(artifact) != locator.get("artifact_digest"):
            raise RegistryIntegrityError("cold archive artifact failed digest verification")

    def resolve(
        self, origin_digest: str, *, prefer_cold: bool = False
    ) -> dict[str, Any]:
        """Resolve an authenticated locator, rechecking cold artifact bytes.

        ``prefer_cold`` may return the supplemental generic archive.  Its
        ``origin_bound`` field remains false: the digest authenticates file
        bytes and locator metadata, not a Run-aware archive manifest.
        """
        if not _valid_digest(origin_digest):
            raise ValueError("origin_digest must be a lowercase SHA-256 digest")
        document = self._snapshot()
        record = document["runs"].get(origin_digest)
        if record is None:
            raise ProvenanceError("unknown Run origin")
        if record["state"] == "deleting":
            raise ProvenanceError("Run origin is being permanently disposed")
        if prefer_cold and record.get("cold_locator") is not None:
            locator = record["cold_locator"]
            self._verify_cold_locator(locator)
            return dict(locator)
        if record["state"] == "archived":
            raise ProvenanceError(
                "legacy archive registration lacks a verified Run-origin binding"
            )
        if record["state"] == "disposed":
            locator = record["tombstone"]
            self.verify_locator(locator)
            return dict(locator)
        locator = {
            "kind": "hot",
            "path": record["hot_path"],
            "origin_digest": origin_digest,
        }
        locator["authentication"] = self.authenticate(locator)
        return locator

    def verify_tombstone(self, tombstone: Any, authentication: str) -> bool:
        if type(tombstone) is not dict or type(authentication) is not str:
            raise RegistryIntegrityError("tombstone is malformed")
        if not hmac.compare_digest(authentication, self.authenticate(tombstone)):
            raise RegistryIntegrityError("tombstone authentication failed")
        return True


def _store_token(connection: sqlite3.Connection) -> dict[str, Any]:
    identity = connection.execute(
        "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
    ).fetchall()
    clock = connection.execute(
        "SELECT mutation FROM sdk_storage_clock WHERE singleton=1"
    ).fetchall()
    if len(identity) != 1 or len(clock) != 1:
        raise ProvenanceError("source storage identity or mutation clock is invalid")
    return {
        "store_id": identity[0][0],
        "incarnation": identity[0][1],
        "mutation": clock[0][0],
    }


def _count(connection: sqlite3.Connection, sql: str, parameters: tuple[Any, ...]) -> int:
    return int(connection.execute(sql, parameters).fetchone()[0])


def _block(blockers: list[dict[str, Any]], code: str, count: int = 1) -> None:
    if count:
        blockers.append({"code": code, "count": count})


def _notification_count(connection: sqlite3.Connection, run_id: str) -> int:
    total = 0
    for row in connection.execute("SELECT payload FROM sdk_notifications"):
        try:
            payload = decode_value(connection, row[0])
        except (ContentIntegrityError, ValueError, sqlite3.DatabaseError) as exc:
            raise ProvenanceError("notification payload cannot be verified") from exc
        if type(payload) is dict and payload.get("run_id") == run_id:
            total += 1
    return total


def _kernel_execution_count(connection: sqlite3.Connection, run_id: str) -> int:
    if connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='kernel_executions'"
    ).fetchone() is None:
        return 0
    total = 0
    for row in connection.execute("SELECT command_json FROM kernel_executions"):
        try:
            command = json.loads(row[0])
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ProvenanceError("Kernel execution identity cannot be verified") from exc
        if type(command) is dict and command.get("correlation_id") == run_id:
            total += 1
    return total


def _build_plan(
    connection: sqlite3.Connection,
    source: Path,
    run_id: str,
    registry_document: dict[str, Any],
) -> dict[str, Any]:
    _validate_source_schema(connection)
    token = _store_token(connection)
    blockers: list[dict[str, Any]] = []
    run = connection.execute(
        "SELECT revision,state FROM sdk_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    if run is None:
        if connection.execute(
            "SELECT 1 FROM sdk_disposed_runs WHERE run_id=?", (run_id,)
        ).fetchone():
            _block(blockers, "already_disposed")
        else:
            _block(blockers, "unknown_run")
        revision = None
        state = None
    else:
        revision, state = run[0], run[1]
        if state not in _RUN_TERMINAL:
            _block(blockers, "run_not_terminal")

    origins = [
        origin
        for origin, record in registry_document["runs"].items()
        if (
            record.get("store_id"), record.get("incarnation"), record.get("run_id")
        ) == (token["store_id"], token["incarnation"], run_id)
    ]
    if len(origins) != 1:
        _block(blockers, "origin_not_uniquely_registered")
        origin = None
    else:
        origin = origins[0]
        record = registry_document["runs"][origin]
        if record["state"] in {"deleting", "disposed"}:
            _block(blockers, "origin_not_active")
        if record["state"] == "archived":
            _block(blockers, "archive_origin_binding_unverified")
        if record["state"] == "active" and record.get("hot_path") != str(source):
            _block(blockers, "origin_hot_path_mismatch")
        incoming = sum(
            1 for reference in registry_document["references"]
            if reference["target"] == origin
        )
        _block(blockers, "incoming_provenance_references", incoming)
    if not registry_document["scope_closed"]:
        _block(blockers, "registry_scope_not_closed")

    checks = (
        ("run_links", "SELECT count(*) FROM sdk_run_links WHERE previous_run_id=? OR next_run_id=?", (run_id, run_id)),
        ("task_or_attempt_records", "SELECT count(*) FROM sdk_run_items WHERE run_id=? AND section IN ('task','attempt')", (run_id,)),
        ("execution_registrations", "SELECT count(*) FROM sdk_executions WHERE run_id=?", (run_id,)),
        ("recovery_records", "SELECT count(*) FROM sdk_recoveries WHERE run_id=?", (run_id,)),
        ("outbox_records", "SELECT count(*) FROM sdk_outbox WHERE run_id=?", (run_id,)),
        ("watch_records", "SELECT count(*) FROM sdk_watches WHERE run_id=?", (run_id,)),
        ("subscription_records", "SELECT count(*) FROM sdk_subscriptions WHERE run_id=?", (run_id,)),
    )
    for code, sql, parameters in checks:
        _block(blockers, code, _count(connection, sql, parameters))
    _block(blockers, "notification_records", _notification_count(connection, run_id))
    related_results = _count(
        connection,
        "SELECT count(*) FROM sdk_results r JOIN sdk_executions e "
        "ON e.execution_id=r.execution_id WHERE e.run_id=?",
        (run_id,),
    )
    _block(blockers, "result_records", related_results)
    _block(blockers, "kernel_execution_evidence", _kernel_execution_count(connection, run_id))
    if connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='runtime_sandbox_journals'"
    ).fetchone():
        _block(
            blockers,
            "external_journal_ownership_unverified",
            _count(connection, "SELECT count(*) FROM runtime_sandbox_journals", ()),
        )

    unsigned = {
        "format_version": 1,
        "source": str(source),
        "run_id": run_id,
        "run_revision": revision,
        "run_state": state,
        "origin_digest": origin,
        "store_token": token,
        "registry_revision": registry_document["revision"],
        "registry_authentication": _digest(registry_document),
        "scope_closed": registry_document["scope_closed"],
        "blockers": blockers,
        "applicable": not blockers,
        "preserves_content_objects": True,
        "external_files_deleted": False,
    }
    return {**unsigned, "plan_digest": _digest(unsigned)}


def plan_disposal(
    source_db: str | os.PathLike[str], run_id: str, registry: ProvenanceRegistry
) -> dict[str, Any]:
    """Build a read-only exact disposal plan for one registered Run."""
    if type(run_id) is not str or not run_id:
        raise ValueError("run_id must be a nonempty string")
    if not isinstance(registry, ProvenanceRegistry):
        raise TypeError("registry must be a ProvenanceRegistry")
    source = Path(source_db).expanduser().resolve(strict=True)
    document = registry._snapshot()
    with closing(_read_only(source)) as connection:
        connection.execute("BEGIN")
        return _build_plan(connection, source, run_id, document)


def _validate_plan(plan: Any) -> tuple[Path, str, str]:
    if type(plan) is not dict or type(plan.get("plan_digest")) is not str:
        raise ProvenanceError("disposal plan is missing its digest")
    unsigned = dict(plan)
    supplied = unsigned.pop("plan_digest")
    if _digest(unsigned) != supplied:
        raise ProvenanceError("disposal plan was modified after it was computed")
    if plan.get("format_version") != 1 or not plan.get("applicable") or plan.get("blockers"):
        raise DisposalBlocked("blocked disposal plan cannot be applied")
    try:
        source = Path(plan["source"]).resolve(strict=True)
    except (KeyError, OSError) as exc:
        raise ProvenanceError("disposal plan source is invalid") from exc
    if type(plan.get("run_id")) is not str or not _valid_digest(plan.get("origin_digest")):
        raise ProvenanceError("disposal plan Run identity is invalid")
    return source, plan["run_id"], plan["origin_digest"]


def _hit(failpoint: _Failpoint | None, stage: str) -> None:
    if failpoint is not None:
        failpoint(stage)


def _read_tombstone(
    connection: sqlite3.Connection,
    run_id: str,
    registry: ProvenanceRegistry,
) -> tuple[dict[str, Any], str] | None:
    row = connection.execute(
        "SELECT tombstone,authentication FROM sdk_disposed_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    if row is None:
        return None
    try:
        tombstone = json.loads(row[0])
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RegistryIntegrityError("source tombstone is invalid JSON") from exc
    if _canonical(tombstone) != row[0]:
        raise RegistryIntegrityError("source tombstone is not canonical")
    registry.verify_tombstone(tombstone, row[1])
    return tombstone, row[1]


def _delete_run(
    connection: sqlite3.Connection,
    run_id: str,
    tombstone: dict[str, Any],
    authentication: str,
) -> dict[str, int]:
    event_ids = [row[0] for row in connection.execute(
        "SELECT sequence FROM sdk_events WHERE run_id=?", (run_id,)
    )]
    revision_ids = [row[0] for row in connection.execute(
        "SELECT revision FROM sdk_run_revisions WHERE run_id=?", (run_id,)
    )]
    deleted: dict[str, int] = {}
    tables = (
        "sdk_run_history", "sdk_run_items", "sdk_run_revisions", "sdk_commands",
        "sdk_events", "sdk_subscriptions", "sdk_event_watermarks",
        "sdk_expired_revisions", "sdk_run_links", "sdk_runs",
    )
    for table in tables:
        if table == "sdk_run_links":
            cursor = connection.execute(
                "DELETE FROM sdk_run_links WHERE previous_run_id=? OR next_run_id=?",
                (run_id, run_id),
            )
        else:
            cursor = connection.execute(f"DELETE FROM {table} WHERE run_id=?", (run_id,))
        deleted[table] = cursor.rowcount
    for sequence in event_ids:
        connection.execute(
            "DELETE FROM sdk_retention_times WHERE category='event' AND record_key=?",
            (str(sequence),),
        )
    for revision in revision_ids:
        connection.execute(
            "DELETE FROM sdk_retention_times WHERE category='revision' AND record_key=?",
            (_canonical([run_id, revision]),),
        )
    connection.execute(
        "INSERT INTO sdk_disposed_runs(run_id,tombstone,authentication) VALUES(?,?,?)",
        (run_id, _canonical(tombstone), authentication),
    )
    return deleted


def dispose_run(
    plan: dict[str, Any],
    registry: ProvenanceRegistry,
    *,
    lease: Lease,
    operation_id: str,
    failpoint: _Failpoint | None = None,
) -> dict[str, Any]:
    """Permanently retire a task-free Run, retaining a signed source tombstone."""
    source, run_id, origin = _validate_plan(plan)
    if not isinstance(registry, ProvenanceRegistry):
        raise TypeError("registry must be a ProvenanceRegistry")
    if not isinstance(lease, Lease):
        raise TypeError("lease must be a maintenance Lease")
    if type(operation_id) is not str or not operation_id.strip():
        raise ValueError("operation_id must be a nonempty string")
    lease.check(source)

    source_connection = sqlite3.connect(source, timeout=30)
    source_connection.row_factory = sqlite3.Row
    try:
        registry_connection = registry._connect()
    except BaseException:
        source_connection.close()
        raise
    try:
        source_connection.execute("BEGIN")
        _validate_source_schema(source_connection)
        source_connection.rollback()
        registry_connection.execute("BEGIN IMMEDIATE")
        document = registry._load_document(registry_connection)
        record = document["runs"].get(origin)
        if record is None:
            raise StaleDisposalPlan("Run origin disappeared from the registry")
        deleting = record["state"] == "deleting"
        if deleting:
            deletion = record.get("deletion")
            if deletion != {"operation_id": operation_id, "plan_digest": plan["plan_digest"]}:
                raise StaleDisposalPlan("Run origin is held by another disposal operation")
        elif record["state"] in {"disposed"}:
            locator = record.get("tombstone")
            if type(locator) is not dict:
                raise RegistryIntegrityError("disposed registry record has no tombstone locator")
            registry.verify_locator(locator)
            signed_tombstone = locator.get("tombstone")
            if (
                type(signed_tombstone) is not dict
                or signed_tombstone.get("operation_id") != operation_id
                or signed_tombstone.get("plan_digest") != plan["plan_digest"]
            ):
                raise StaleDisposalPlan("disposed Run belongs to another operation or plan")
            registry_connection.rollback()
            return {
                "operation_id": operation_id,
                "run_id": run_id,
                "origin_digest": origin,
                "tombstone": locator,
                "idempotent_replay": True,
            }
        elif document["revision"] != plan["registry_revision"]:
            raise StaleDisposalPlan("provenance registry changed after planning")

        source_connection.execute("BEGIN IMMEDIATE")
        _validate_source_schema(source_connection)
        existing_tombstone = _read_tombstone(
            source_connection, run_id, registry
        )
        if existing_tombstone is None:
            recomputed = _build_plan(source_connection, source, run_id, document)
            if deleting:
                # The durable deleting marker is the only expected blocker on
                # retry.  Unrelated registry revisions may advance, but source
                # identity/state and every safety check must still match.
                retry_blockers = [
                    blocker for blocker in recomputed["blockers"]
                    if blocker["code"] != "origin_not_active"
                ]
                if (
                    retry_blockers
                    or recomputed["source"] != plan["source"]
                    or recomputed["run_id"] != plan["run_id"]
                    or recomputed["run_revision"] != plan["run_revision"]
                    or recomputed["run_state"] != plan["run_state"]
                    or recomputed["origin_digest"] != plan["origin_digest"]
                    or recomputed["store_token"] != plan["store_token"]
                    or not recomputed["scope_closed"]
                ):
                    raise StaleDisposalPlan("source or provenance changed after planning")
            elif recomputed != plan:
                raise StaleDisposalPlan("source or provenance changed after planning")

            if not deleting:
                record["state"] = "deleting"
                record["deletion"] = {
                    "operation_id": operation_id,
                    "plan_digest": plan["plan_digest"],
                }
                registry._store_document(registry_connection, document)
                registry_connection.commit()
                # Reacquire the global writer lock.  Other writers can observe
                # the durable deleting state but cannot add a reference to it.
                registry_connection.execute("BEGIN IMMEDIATE")
                document = registry._load_document(registry_connection)
                record = document["runs"][origin]
            lease.check(source)
            tombstone = {
                "format_version": 1,
                "operation_id": operation_id,
                "origin_digest": origin,
                "run_id": run_id,
                "store_id": plan["store_token"]["store_id"],
                "incarnation": plan["store_token"]["incarnation"],
                "final_revision": plan["run_revision"],
                "final_state": plan["run_state"],
                "disposed_at": time.time(),
                "plan_digest": plan["plan_digest"],
                "content_objects_preserved": True,
            }
            authentication = registry.authenticate(tombstone)
            deleted = _delete_run(
                source_connection, run_id, tombstone, authentication
            )
            _hit(failpoint, "before_source_commit")
            lease.check(source)
            source_connection.commit()
            _hit(failpoint, "after_source_commit")
        else:
            tombstone, authentication = existing_tombstone
            if (
                tombstone.get("operation_id") != operation_id
                or tombstone.get("origin_digest") != origin
                or tombstone.get("plan_digest") != plan["plan_digest"]
            ):
                raise StaleDisposalPlan("source tombstone belongs to another disposal")
            deleted = {}
            source_connection.rollback()

        locator = {
            "kind": "disposed",
            "path": str(source),
            "origin_digest": origin,
            "run_id": run_id,
            "tombstone": tombstone,
            "source_authentication": authentication,
        }
        locator["authentication"] = registry.authenticate(locator)
        record = document["runs"][origin]
        record["state"] = "disposed"
        record["hot_path"] = str(source)
        record["cold_locator"] = None
        record["deletion"] = None
        record["tombstone"] = locator
        document["references"] = [
            reference for reference in document["references"]
            if reference["source"] != origin
        ]
        registry._store_document(registry_connection, document)
        registry_connection.commit()
        return {
            "operation_id": operation_id,
            "run_id": run_id,
            "origin_digest": origin,
            "deleted": deleted,
            "tombstone": locator,
            "idempotent_replay": existing_tombstone is not None,
            "content_objects_preserved": True,
            "external_files_deleted": False,
        }
    except BaseException:
        source_connection.rollback()
        registry_connection.rollback()
        raise
    finally:
        source_connection.close()
        registry_connection.close()


__all__ = [
    "DisposalBlocked",
    "ProvenanceError",
    "ProvenanceRegistry",
    "RegistryIntegrityError",
    "StaleDisposalPlan",
    "dispose_run",
    "plan_disposal",
]
