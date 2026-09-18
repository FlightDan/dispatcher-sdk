"""Conservative, single-store retention planning and application.

The planner is read-only and bounded.  The applier treats its input as an
untrusted proposal: under an exclusive maintenance lease and one SQLite write
transaction it recomputes the complete plan before deleting anything.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from .content import (CONTENT_PREFIX, ContentIntegrityError, decode_value,
                      MAX_DEPTH, MAX_LOGICAL_BYTES, _Decoder, _object_digest)
from .maintenance import Lease


class RetentionError(RuntimeError):
    """A retention plan is invalid, unsafe, stale, or cannot be applied."""


class IncompleteRetentionPlan(RetentionError):
    """The bounded scan did not establish a complete deletion set."""


class StaleRetentionPlan(RetentionError):
    """The store changed after the plan was produced."""


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Count-based retention for the two initially supported record classes."""

    history_revisions: int | None = None
    decision_events: int | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("history_revisions", self.history_revisions),
            ("decision_events", self.decision_events),
        ):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer or None")

    def to_dict(self) -> dict[str, int | None]:
        return {
            "history_revisions": self.history_revisions,
            "decision_events": self.decision_events,
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class _BudgetExceeded(Exception):
    def __init__(self, table: str) -> None:
        self.table = table


class _Scanner:
    def __init__(self, connection: sqlite3.Connection, limit: int) -> None:
        self.connection = connection
        self.limit = limit
        self.used = 0
        self.bytes_used = 0
        self.byte_limit = 64 * 1024 * 1024

    def rows(self, sql: str, parameters: tuple[Any, ...], table: str) -> list[sqlite3.Row]:
        remaining = self.limit - self.used
        description = self.connection.execute(sql + " LIMIT 0", parameters).description
        columns = ['"' + item[0].replace('"', '""') + '"' for item in description]
        size = " + ".join(
            f"CASE WHEN typeof({column}) IN ('text','blob') "
            f"THEN length(CAST({column} AS BLOB)) ELSE 8 END" for column in columns)
        available = self.byte_limit - self.bytes_used
        # Oversized records are measured in SQLite but their bodies are never
        # transferred to Python. Stream rows; do not materialize LIMIT rows first.
        selections = [f"CASE WHEN ({size}) <= {available} THEN {column} ELSE NULL END AS {column}"
                      for column in columns]
        query = f"SELECT {','.join(selections)}, ({size}) AS _sdk_scan_bytes FROM ({sql}) LIMIT ?"
        rows = []
        for row in self.connection.execute(query, (*parameters, remaining + 1)):
            if len(rows) >= remaining:
                raise _BudgetExceeded(table)
            if row[-1] > self.byte_limit - self.bytes_used:
                raise _BudgetExceeded(f"{table} (64 MiB stored-payload byte budget)")
            self.bytes_used += row[-1]
            self.used += 1
            rows.append(row)
        return rows


_REQUIRED_COLUMNS = {
    "sdk_runs": {"run_id", "revision", "state"},
    "sdk_run_revisions": {"run_id", "revision"},
    "sdk_run_items": {"run_id", "section", "item_key", "value"},
    "sdk_run_history": {"run_id", "section", "item_key", "revision", "value"},
    "sdk_commands": {"run_id", "command_id", "digest", "response"},
    "sdk_events": {"sequence", "run_id", "revision", "kind", "payload"},
    "sdk_subscriptions": {"run_id", "name", "cursor"},
    "sdk_recoveries": {"decision", "application_state", "manifest"},
    "sdk_content_objects": {"digest", "encoded", "logical_bytes"},
    "sdk_storage_identity": {"singleton", "store_id", "incarnation"},
    "sdk_storage_clock": {"singleton", "mutation"},
    "sdk_event_watermarks": {"run_id", "high_water", "expired_through"},
    "sdk_expired_revisions": {"run_id", "revision"},
    "sdk_disposed_runs": {"run_id", "tombstone", "authentication"},
    "sdk_maintenance_receipts": {"operation_id", "plan_digest", "result"},
}


def _validate_schema(connection: sqlite3.Connection) -> None:
    from .orchestrator.engine import Orchestrator
    try:
        Orchestrator.__new__(Orchestrator)._validate_existing_store(connection)
    except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
        raise RetentionError("retention requires the exact supported schema and trigger bodies") from error
    try:
        marker = connection.execute(
            "SELECT component,version FROM sdk_schema_meta"
        ).fetchall()
    except sqlite3.DatabaseError as error:
        raise RetentionError("database is not an orchestrator schema v3 store") from error
    if len(marker) != 1 or tuple(marker[0]) != ("orchestrator", 3):
        raise RetentionError("retention requires orchestrator schema version 3")
    tables = {str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'"
    )}
    missing = sorted(set(_REQUIRED_COLUMNS) - tables)
    if missing:
        raise RetentionError(f"retention schema is missing tables: {', '.join(missing)}")
    for table, required in _REQUIRED_COLUMNS.items():
        escaped = table.replace('"', '""')
        actual = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{escaped}")')}
        absent = required - actual
        if absent:
            raise RetentionError(
                f"retention schema table {table} is missing columns: {', '.join(sorted(absent))}"
            )
    trigger_names = {str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='trigger'"
    )}
    for table in _REQUIRED_COLUMNS:
        if table == "sdk_storage_clock":
            continue
        for action in ("insert", "update", "delete"):
            if f"{table}_track_{action}" not in trigger_names:
                raise RetentionError(
                    f"retention requires the mutation trigger {table}_track_{action}"
                )


def _token(connection: sqlite3.Connection) -> dict[str, Any]:
    identities = connection.execute(
        "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
    ).fetchall()
    clocks = connection.execute(
        "SELECT mutation FROM sdk_storage_clock WHERE singleton=1"
    ).fetchall()
    if len(identities) != 1 or len(clocks) != 1 or type(clocks[0][0]) is not int:
        raise RetentionError("storage identity or mutation clock is invalid")
    return {
        "store_id": str(identities[0][0]),
        "incarnation": str(identities[0][1]),
        "mutation": int(clocks[0][0]),
    }


def _read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
    except BaseException:
        connection.close()
        raise
    return connection


def _parse_receipt(response: Any) -> tuple[str, int]:
    if type(response) is not str:
        raise RetentionError("command receipt response is not stored as text")
    try:
        value = json.loads(response)
    except (TypeError, ValueError) as error:
        raise RetentionError("command receipt response is not valid JSON") from error
    if (type(value) is not dict or set(value) != {"run_id", "revision"}
            or type(value["run_id"]) is not str or not value["run_id"]
            or type(value["revision"]) is not int or value["revision"] < 0):
        raise RetentionError("command receipt response has an invalid revision reference")
    return value["run_id"], value["revision"]


class _ContentGraph:
    """Validate a bounded stored DAG without hydrating repeated logical trees."""

    def __init__(self, connection, objects):
        self.objects = objects
        self.validator = _Decoder(connection, MAX_LOGICAL_BYTES, MAX_DEPTH)
        self.nodes = {}
        for identity, (encoded, length) in objects.items():
            node = self.validator.parse(encoded, f"content object {identity}")
            if _object_digest(encoded) != identity:
                raise ContentIntegrityError("content object digest mismatch")
            measured = self.validator.measure(node)
            if measured != length or not 0 <= length <= MAX_LOGICAL_BYTES:
                raise ContentIntegrityError("content object logical length mismatch")
            self.nodes[identity] = node
        self.heights = {}

    def walk(self, node, reachable, active=None):
        active = set() if active is None else active
        tag = node[0]
        if tag == "ref":
            identity, expected = self.validator._reference_fields(node)
            if identity in active or len(active) >= MAX_DEPTH:
                raise ContentIntegrityError("content object cycle or excessive reference depth")
            if identity not in self.objects or self.objects[identity][1] != expected:
                raise ContentIntegrityError("content reference is missing or has an invalid length")
            reachable.add(identity)
            if identity in self.heights:
                # Reachability must still include descendants when a caller
                # previously validated an orphan against a different root set.
                height, reference_height, descendants = self.heights[identity]
                reachable.update(descendants)
                return height, reference_height
            active.add(identity)
            descendants = set()
            try:
                height, reference_height = self.walk(self.nodes[identity], descendants, active)
            finally:
                active.remove(identity)
            reference_height += 1
            if reference_height > MAX_DEPTH:
                raise ContentIntegrityError("content exceeds maximum reference depth")
            self.heights[identity] = (height, reference_height, descendants)
            reachable.update(descendants)
            return height, reference_height
        if tag == "list":
            children = node[1]
        elif tag == "dict":
            children = [entry[1] for entry in node[1]]
        else:
            return 0, 0
        heights = [self.walk(child, reachable, active) for child in children]
        height = 1 + max((item[0] for item in heights), default=0)
        reference_height = max((item[1] for item in heights), default=0)
        if height > MAX_DEPTH:
            raise ContentIntegrityError("content exceeds maximum logical depth")
        return height, reference_height

    def references(self, encoded):
        if not encoded.startswith(CONTENT_PREFIX):
            # Legacy inline records cannot contain codec references.
            decode_value(self.validator.connection, encoded)
            return set()
        node = self.validator.parse(encoded[len(CONTENT_PREFIX):], "content root")
        if self.validator.measure(node) > MAX_LOGICAL_BYTES:
            raise ContentIntegrityError("content exceeds logical byte bound")
        reachable = set()
        self.walk(node, reachable)
        return reachable


def _finish_plan(plan: dict[str, Any]) -> dict[str, Any]:
    operation_seed = _digest(plan)
    plan["operation_id"] = f"retention-{operation_seed[:32]}"
    plan["plan_digest"] = _digest(plan)
    return plan


def _blocked_plan(
    path: Path,
    run_id: str,
    policy: RetentionPolicy,
    scan_limit: int,
    token: dict[str, Any],
    rows_scanned: int,
    message: str,
) -> dict[str, Any]:
    return _finish_plan({
        "format_version": 1,
        "path": str(path),
        "run_id": run_id,
        "schema_version": 3,
        "policy": policy.to_dict(),
        "policy_digest": _digest(policy.to_dict()),
        "scan": {"limit": scan_limit, "rows_scanned": rows_scanned, "complete": False},
        "token": token,
        "applicable": False,
        "blockers": [message],
        "candidates": {"history": [], "revisions": [], "events": [], "content_objects": []},
        "protected": {
            "revisions": [], "history": [], "events": [], "content_objects": [],
            "disposed_runs": [],
        },
        "limitations": [
            "Command receipts are retained indefinitely and can pin every historical revision.",
            "This plan covers one orchestrator store only; it does not prune attempts, commands, recoveries, Effects, or other stores.",
        ],
    })


def _build_plan(
    connection: sqlite3.Connection,
    path: Path,
    run_id: str,
    policy: RetentionPolicy,
    scan_limit: int,
) -> dict[str, Any]:
    _validate_schema(connection)
    token = _token(connection)
    if connection.execute(
        "SELECT 1 FROM sdk_disposed_runs WHERE run_id=?", (run_id,)
    ).fetchone() is not None:
        raise RetentionError("cannot plan retention for a permanently disposed run")
    run = connection.execute(
        "SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    if run is None:
        raise RetentionError("unknown run")
    current_revision = int(run[0])
    scanner = _Scanner(connection, scan_limit)
    try:
        revisions = scanner.rows(
            "SELECT revision FROM sdk_run_revisions WHERE run_id=?", (run_id,),
            "sdk_run_revisions",
        )
        commands = scanner.rows(
            "SELECT run_id,command_id,response FROM sdk_commands", (), "sdk_commands"
        )
        histories = scanner.rows(
            "SELECT run_id,section,item_key,revision,value FROM sdk_run_history", (),
            "sdk_run_history",
        )
        items = scanner.rows(
            "SELECT run_id,section,item_key,value FROM sdk_run_items", (), "sdk_run_items"
        )
        events = scanner.rows(
            "SELECT sequence,run_id,revision,kind,payload FROM sdk_events", (), "sdk_events"
        )
        subscriptions = scanner.rows(
            "SELECT run_id,name,cursor FROM sdk_subscriptions", (), "sdk_subscriptions"
        )
        recoveries = scanner.rows(
            "SELECT recovery_id,decision,application_state,manifest FROM sdk_recoveries", (),
            "sdk_recoveries",
        )
        content_rows = scanner.rows(
            "SELECT digest,encoded,logical_bytes FROM sdk_content_objects", (),
            "sdk_content_objects",
        )
        disposed_rows = scanner.rows(
            "SELECT run_id,tombstone,authentication FROM sdk_disposed_runs", (),
            "sdk_disposed_runs",
        )
    except _BudgetExceeded as error:
        return _blocked_plan(
            path, run_id, policy, scan_limit, token, scanner.used,
            f"scan limit reached while reading {error.table}; no deletion set is authorized",
        )

    revision_values = {int(row[0]) for row in revisions}
    if current_revision not in revision_values:
        return _blocked_plan(path, run_id, policy, scan_limit, token, scanner.used,
                             "current revision is absent from sdk_run_revisions")

    reasons: dict[int, set[str]] = {current_revision: {"current_revision"}}
    receipt_counts = 0
    try:
        for command in commands:
            referenced_run, referenced_revision = _parse_receipt(command["response"])
            if referenced_run == run_id:
                receipt_counts += 1
                reasons.setdefault(referenced_revision, set()).add(
                    f"command_receipt:{command['run_id']}:{command['command_id']}"
                )
    except RetentionError as error:
        return _blocked_plan(path, run_id, policy, scan_limit, token, scanner.used, str(error))

    if policy.history_revisions is None:
        for revision in revision_values:
            reasons.setdefault(revision, set()).add("policy_preserves_all_history")
    elif policy.history_revisions:
        for revision in sorted(revision_values)[-policy.history_revisions:]:
            reasons.setdefault(revision, set()).add("policy_recent_revision")
    missing_roots = sorted(set(reasons) - revision_values)
    if missing_roots:
        return _blocked_plan(
            path, run_id, policy, scan_limit, token, scanner.used,
            f"protected revisions are missing: {missing_roots}",
        )

    protected_revisions = set(reasons)
    target_history = [row for row in histories if row["run_id"] == run_id]
    malformed = (
        any(type(row["value"]) is not str for row in histories)
        or any(type(row["value"]) is not str for row in items)
        or any(type(row["payload"]) is not str for row in events)
        or any(type(row["decision"]) is not str or type(row["manifest"]) is not str
               or (row["application_state"] is not None
                   and type(row["application_state"]) is not str)
               for row in recoveries)
    )
    if malformed:
        return _blocked_plan(
            path, run_id, policy, scan_limit, token, scanner.used,
            "codec-bearing fields have invalid SQLite storage types",
        )
    history_roots: dict[tuple[str, str, int], set[int]] = {}
    by_field: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in target_history:
        by_field.setdefault((str(row["section"]), str(row["item_key"])), []).append(row)
    for field, rows in by_field.items():
        ordered = sorted(rows, key=lambda value: int(value["revision"]))
        for revision in protected_revisions:
            eligible = [row for row in ordered if int(row["revision"]) <= revision]
            if eligible:
                baseline = eligible[-1]
                key = (field[0], field[1], int(baseline["revision"]))
                history_roots.setdefault(key, set()).add(revision)

    history_candidates = []
    protected_history = []
    candidate_history_keys: set[tuple[str, str, str, int]] = set()
    for row in target_history:
        key = (str(row["section"]), str(row["item_key"]), int(row["revision"]))
        record = {
            "run_id": run_id, "section": key[0], "item_key": key[1], "revision": key[2],
            "stored_bytes": len(str(row["value"]).encode("utf-8")),
        }
        required_for = history_roots.get(key)
        if required_for:
            record["reasons"] = [f"baseline_for_revision:{value}" for value in sorted(required_for)]
            protected_history.append(record)
        else:
            history_candidates.append(record)
            candidate_history_keys.add((run_id, key[0], key[1], key[2]))

    revision_candidates = [
        {"run_id": run_id, "revision": revision}
        for revision in sorted(revision_values - protected_revisions)
    ]

    target_decisions = sorted(
        [row for row in events if row["run_id"] == run_id and row["kind"] == "application.decided"],
        key=lambda row: int(row["sequence"]),
    )
    retained_event_sequences: set[int] = set()
    event_reasons: dict[int, list[str]] = {}
    if policy.decision_events is None:
        for row in target_decisions:
            sequence = int(row["sequence"])
            retained_event_sequences.add(sequence)
            event_reasons.setdefault(sequence, []).append("policy_preserves_all_decision_events")
    elif policy.decision_events:
        for row in target_decisions[-policy.decision_events:]:
            sequence = int(row["sequence"])
            retained_event_sequences.add(sequence)
            event_reasons.setdefault(sequence, []).append("policy_recent_decision_event")
    target_subscriptions = [row for row in subscriptions if row["run_id"] == run_id]
    for row in target_decisions:
        sequence = int(row["sequence"])
        for subscription in target_subscriptions:
            if int(subscription["cursor"]) < sequence:
                retained_event_sequences.add(sequence)
                event_reasons.setdefault(sequence, []).append(
                    f"subscription:{subscription['name']}:cursor:{subscription['cursor']}"
                )
    event_candidates = []
    protected_events = []
    candidate_event_sequences: set[int] = set()
    for row in target_decisions:
        sequence = int(row["sequence"])
        record = {
            "sequence": sequence, "run_id": run_id, "revision": int(row["revision"]),
            "kind": "application.decided",
            "stored_bytes": len(str(row["payload"]).encode("utf-8")),
        }
        if sequence in retained_event_sequences:
            record["reasons"] = sorted(event_reasons[sequence])
            protected_events.append(record)
        else:
            event_candidates.append(record)
            candidate_event_sequences.add(sequence)

    objects: dict[str, tuple[str, int]] = {}
    try:
        for row in content_rows:
            digest, encoded, logical_bytes = row[0], row[1], row[2]
            if type(digest) is not str or type(encoded) is not str or type(logical_bytes) is not int:
                raise ContentIntegrityError("content object has invalid stored types")
            objects[digest] = (encoded, logical_bytes)
        graph = _ContentGraph(connection, objects)
        # Validate orphan DAGs too, without expanding their logical payloads.
        for identity, (_, logical_bytes) in objects.items():
            graph.walk(["ref", identity, logical_bytes], set())

        all_roots: list[str] = [str(row["value"]) for row in items]
        all_roots.extend(
            str(row["value"]) for row in histories
            if (str(row["run_id"]), str(row["section"]), str(row["item_key"]),
                int(row["revision"])) not in candidate_history_keys
        )
        all_roots.extend(
            str(row["payload"]) for row in events
            if int(row["sequence"]) not in candidate_event_sequences
        )
        for row in recoveries:
            all_roots.append(str(row["decision"]))
            all_roots.append(str(row["manifest"]))
            if row["application_state"] is not None:
                all_roots.append(str(row["application_state"]))

        reachable: set[str] = set()
        for encoded in all_roots:
            reachable.update(graph.references(encoded))
    except (ContentIntegrityError, TypeError, ValueError, RecursionError) as error:
        return _blocked_plan(
            path, run_id, policy, scan_limit, token, scanner.used,
            f"content validation failed: {error}",
        )

    gc_enabled = policy.history_revisions is not None or policy.decision_events is not None
    object_candidates = []
    protected_objects = []
    if gc_enabled:
        for digest in sorted(set(objects) - reachable):
            encoded, logical_bytes = objects[digest]
            object_candidates.append({
                "digest": digest,
                "stored_bytes": len(encoded.encode("utf-8")),
                "logical_bytes": logical_bytes,
            })
    for digest in sorted(set(objects) - {row["digest"] for row in object_candidates}):
        encoded, logical_bytes = objects[digest]
        protected_objects.append({
            "digest": digest,
            "stored_bytes": len(encoded.encode("utf-8")),
            "logical_bytes": logical_bytes,
            "reasons": (["reachable_from_retained_records"] if digest in reachable
                        else ["object_gc_disabled_by_policy"]),
        })

    plan = {
        "format_version": 1,
        "path": str(path),
        "run_id": run_id,
        "schema_version": 3,
        "policy": policy.to_dict(),
        "policy_digest": _digest(policy.to_dict()),
        "scan": {"limit": scan_limit, "rows_scanned": scanner.used, "complete": True,
                 "byte_limit": scanner.byte_limit, "stored_bytes_scanned": scanner.bytes_used},
        "token": token,
        "applicable": True,
        "blockers": [],
        "candidates": {
            "history": sorted(history_candidates,
                              key=lambda row: (row["section"], row["item_key"], row["revision"])),
            "revisions": revision_candidates,
            "events": event_candidates,
            "content_objects": object_candidates,
        },
        "protected": {
            "revisions": [
                {"run_id": run_id, "revision": revision, "reasons": sorted(reasons[revision])}
                for revision in sorted(protected_revisions)
            ],
            "history": sorted(protected_history,
                              key=lambda row: (row["section"], row["item_key"], row["revision"])),
            "events": protected_events,
            "content_objects": protected_objects,
            "disposed_runs": sorted([
                {
                    "run_id": str(row["run_id"]),
                    "stored_bytes": len(str(row["tombstone"]).encode("utf-8"))
                                    + len(str(row["authentication"]).encode("utf-8")),
                    "reasons": ["permanent_identity_tombstone"],
                }
                for row in disposed_rows
            ], key=lambda row: row["run_id"]),
        },
        "summary": {
            "receipt_revision_roots": receipt_counts,
            "history_candidates": len(history_candidates),
            "revision_candidates": len(revision_candidates),
            "event_candidates": len(event_candidates),
            "content_object_candidates": len(object_candidates),
        },
        "limitations": [
            "Command receipts are retained indefinitely and can pin every historical revision.",
            "Current items, commands, attempts, recoveries, and non-target runs are fully retained.",
            "Permanent Run tombstones and their authentication metadata are always retained.",
            "This plan covers one orchestrator store only and makes no cross-store, age-based, Effects, attempt, or physical compaction promise.",
        ],
    }
    return _finish_plan(plan)


def plan_retention(
    path: str | os.PathLike[str],
    run_id: str,
    policy: RetentionPolicy,
    *,
    scan_limit: int = 100_000,
) -> dict[str, Any]:
    """Build an exact, bounded, read-only plan for one orchestrator Run."""
    if type(policy) is not RetentionPolicy:
        raise TypeError("policy must be a RetentionPolicy")
    if type(run_id) is not str or not run_id:
        raise ValueError("run_id must be a nonempty string")
    if type(scan_limit) is not int or scan_limit < 0:
        raise ValueError("scan_limit must be a nonnegative integer")
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"retention requires an existing database: {database}")
    connection = _read_only(database)
    try:
        connection.execute("BEGIN")
        return _build_plan(connection, database, run_id, policy, scan_limit)
    finally:
        connection.rollback()
        connection.close()


def _policy_from_plan(value: Any) -> RetentionPolicy:
    if type(value) is not dict or set(value) != {"history_revisions", "decision_events"}:
        raise RetentionError("plan policy is invalid")
    try:
        return RetentionPolicy(
            history_revisions=value["history_revisions"],
            decision_events=value["decision_events"],
        )
    except ValueError as error:
        raise RetentionError(str(error)) from error


def _validate_plan_document(plan: Any, path: Path) -> tuple[str, RetentionPolicy, int]:
    if type(plan) is not dict:
        raise RetentionError("plan must be a JSON object")
    supplied_digest = plan.get("plan_digest")
    if type(supplied_digest) is not str:
        raise RetentionError("plan digest is missing")
    unsigned = dict(plan)
    del unsigned["plan_digest"]
    if _digest(unsigned) != supplied_digest:
        raise RetentionError("plan was modified after its digest was computed")
    if plan.get("path") != str(path) or type(plan.get("run_id")) is not str:
        raise RetentionError("plan belongs to another database path or has an invalid run")
    if plan.get("format_version") != 1 or plan.get("schema_version") != 3:
        raise RetentionError("unsupported retention plan format or schema")
    policy = _policy_from_plan(plan.get("policy"))
    if plan.get("policy_digest") != _digest(policy.to_dict()):
        raise RetentionError("plan policy digest is invalid")
    scan = plan.get("scan")
    if type(scan) is not dict or type(scan.get("limit")) is not int or scan["limit"] < 0:
        raise RetentionError("plan scan limit is invalid")
    if not plan.get("applicable") or not scan.get("complete"):
        raise IncompleteRetentionPlan("incomplete or blocked retention plan cannot be applied")
    operation_id = plan.get("operation_id")
    if type(operation_id) is not str or not operation_id:
        raise RetentionError("plan operation identity is invalid")
    return plan["run_id"], policy, scan["limit"]


def apply_retention(
    path: str | os.PathLike[str],
    plan: dict[str, Any],
    *,
    lease: Lease,
) -> dict[str, Any]:
    """Apply an exact recomputed plan under an exclusive maintenance lease."""
    database = Path(path).expanduser().resolve()
    run_id, policy, scan_limit = _validate_plan_document(plan, database)
    if not isinstance(lease, Lease):
        raise TypeError("lease must be a maintenance Lease")
    lease.check(database)
    connection = sqlite3.connect(database, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        _validate_schema(connection)
        receipt = connection.execute(
            "SELECT plan_digest,result FROM sdk_maintenance_receipts WHERE operation_id=?",
            (plan["operation_id"],),
        ).fetchone()
        if receipt is not None:
            if receipt["plan_digest"] != plan["plan_digest"]:
                raise RetentionError("maintenance operation identity has a different plan")
            result = json.loads(receipt["result"])
            connection.rollback()
            return result

        recomputed = _build_plan(connection, database, run_id, policy, scan_limit)
        if recomputed != plan:
            raise StaleRetentionPlan("retention plan is stale or does not match authoritative candidates")
        lease.check(database)

        candidates = recomputed["candidates"]
        deleted = {"history": 0, "revisions": 0, "events": 0, "content_objects": 0}
        for record in candidates["history"]:
            cursor = connection.execute(
                "DELETE FROM sdk_run_history WHERE run_id=? AND section=? AND item_key=? AND revision=?",
                (record["run_id"], record["section"], record["item_key"], record["revision"]),
            )
            if cursor.rowcount != 1:
                raise StaleRetentionPlan("history candidate changed during retention")
            deleted["history"] += 1
        for record in candidates["revisions"]:
            connection.execute(
                "INSERT INTO sdk_expired_revisions(run_id,revision) VALUES(?,?)",
                (record["run_id"], record["revision"]),
            )
            cursor = connection.execute(
                "DELETE FROM sdk_run_revisions WHERE run_id=? AND revision=?",
                (record["run_id"], record["revision"]),
            )
            if cursor.rowcount != 1:
                raise StaleRetentionPlan("revision candidate changed during retention")
            connection.execute(
                "DELETE FROM sdk_retention_times WHERE category='revision' AND record_key=?",
                (_canonical([record["run_id"], record["revision"]]),),
            )
            deleted["revisions"] += 1
        for record in candidates["events"]:
            cursor = connection.execute(
                "DELETE FROM sdk_events WHERE sequence=? AND run_id=? AND kind='application.decided'",
                (record["sequence"], record["run_id"]),
            )
            if cursor.rowcount != 1:
                raise StaleRetentionPlan("event candidate changed during retention")
            connection.execute(
                "DELETE FROM sdk_retention_times WHERE category='event' AND record_key=?",
                (str(record["sequence"]),),
            )
            deleted["events"] += 1
        if candidates["events"]:
            expired_through = max(record["sequence"] for record in candidates["events"])
            cursor = connection.execute(
                "UPDATE sdk_event_watermarks SET expired_through=MAX(expired_through,?) WHERE run_id=?",
                (expired_through, run_id),
            )
            if cursor.rowcount != 1:
                raise RetentionError("event watermark is missing")
        for record in candidates["content_objects"]:
            cursor = connection.execute(
                "DELETE FROM sdk_content_objects WHERE digest=?", (record["digest"],)
            )
            if cursor.rowcount != 1:
                raise StaleRetentionPlan("content object candidate changed during retention")
            deleted["content_objects"] += 1

        lease.check(database)
        result = {
            "operation_id": plan["operation_id"],
            "plan_digest": plan["plan_digest"],
            "run_id": run_id,
            "deleted": deleted,
            "event_expired_through": (
                max(record["sequence"] for record in candidates["events"])
                if candidates["events"] else None
            ),
            "idempotent_replay": False,
        }
        connection.execute(
            "INSERT INTO sdk_maintenance_receipts(operation_id,plan_digest,result) VALUES(?,?,?)",
            (plan["operation_id"], plan["plan_digest"], _canonical(result)),
        )
        lease.check(database)
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


__all__ = [
    "RetentionError", "IncompleteRetentionPlan", "StaleRetentionPlan",
    "RetentionPolicy", "plan_retention", "apply_retention",
]
