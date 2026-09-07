"""Read-only runtime identity and deployment compatibility observations.

Verdicts are preflight facts, not permission tokens: writers still enforce their
schema, binding, revision and fence checks. Separate paths are separate snapshots.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import base64
import hashlib
from importlib import metadata
from pathlib import Path
import sqlite3
from typing import Any, Literal, Mapping

from . import _version
from .durability import Durability, validate_durability
from .execution_kernel._registry import Handler, handler_revision, normalize_handlers, registry_revision
from .execution_kernel.contracts import SCHEMA_VERSION
from .storage import _read_only, inspect_storage

VerdictStatus = Literal["supported", "unsupported", "unknown", "not_checked", "not_applicable"]


@dataclass(frozen=True)
class CapabilityVerdict:
    status: VerdictStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class HandlerBindingIdentity:
    handler_id: str
    contract_version: int
    revision: str


@dataclass(frozen=True)
class ModuleIdentity:
    distribution_version: str | None
    module_path: str
    source_version: str | None
    version_agreement: Literal["match", "mismatch", "unknown"]
    source_sha256: str | None
    source_evidence: str
    distribution_record: Literal["verified", "mismatch", "unknown"]
    # Hashes describe files observed now, not in-memory monkeypatches or native dependencies.
    build_verification: str


@dataclass(frozen=True)
class DurabilityObservation:
    configured: Durability | None
    journal_mode: str | None
    other_connections_synchronous: Literal["unknown"] = "unknown"
    hardware_guarantee: Literal["not_checked"] = "not_checked"


@dataclass(frozen=True)
class StorageIdentity:
    name: str
    path: str
    observed_at: str
    completed_at: str
    status: Literal["missing", "recognized", "unsupported", "damaged", "unknown"]
    exists: bool | None
    schemas: dict[str, int | str]
    integrity: Literal["ok", "failed", "unknown"]
    bindings: Literal["checked", "not_checked", "unknown"]
    facts: dict[str, Any]
    durability: DurabilityObservation
    read: CapabilityVerdict
    execute: CapabilityVerdict
    resume: CapabilityVerdict
    # SQLite catalog recognition is not a legacy Run reader.
    summary: CapabilityVerdict
    table_names: tuple[str, ...]
    summary_truncated: bool
    summary_observed_at: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeIdentityReport:
    observed_at: str
    completed_at: str
    module: ModuleIdentity
    contracts: dict[str, int]
    registry_revision: str | None
    handler_bindings: tuple[HandlerBindingIdentity, ...]
    storages: tuple[StorageIdentity, ...]
    read: CapabilityVerdict
    execute: CapabilityVerdict
    resume: CapabilityVerdict
    snapshot_scope: str = "independent_storage_snapshots; catalog_summary_is_a_separate_snapshot"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report (no callable or connection objects)."""
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_identity() -> ModuleIdentity:
    root = Path(__file__).resolve().parent
    try:
        distribution = metadata.distribution("dispatcher-sdk")
        installed_version = distribution.version
    except metadata.PackageNotFoundError:
        distribution = None
        installed_version = None
    declared = getattr(_version, "SOURCE_VERSION", None)
    if not isinstance(declared, str) or not declared:
        declared = None
    agreement = "unknown" if installed_version is None or declared is None else (
        "match" if installed_version == declared else "mismatch")
    source_hash = None
    record_status = "unknown"
    try:
        sources = sorted(root.rglob("*.py"))
        if not sources:
            raise OSError("no readable Python source")
        digest = hashlib.sha256()
        records = {} if distribution is None else {
            str(item): item.hash for item in distribution.files or ()
            if str(item).startswith("dispatcher_sdk/") and str(item).endswith(".py")
        }
        complete_record = bool(records)
        record_mismatch = False
        actual_names = set()
        for path in sources:
            relative = path.relative_to(root).as_posix()
            record_name = "dispatcher_sdk/" + relative
            actual_names.add(record_name)
            content = path.read_bytes()
            # Framing makes path/content boundaries unambiguous and location-independent.
            name = relative.encode("utf-8")
            digest.update(len(name).to_bytes(8, "big") + name)
            digest.update(len(content).to_bytes(8, "big") + content)
            expected = records.get(record_name)
            if expected is None or expected.mode != "sha256":
                complete_record = False
            elif base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=") != expected.value:
                record_mismatch = True
        if records and actual_names != set(records):
            record_mismatch = True
        source_hash = digest.hexdigest()
        record_status = "mismatch" if record_mismatch else ("verified" if complete_record else "unknown")
    except OSError:
        pass
    return ModuleIdentity(installed_version, str(root / "__init__.py"), declared, agreement,
        source_hash, "observed_python_source_tree_sha256+package_source_version_declaration" if source_hash else "unknown",
        record_status, "wheel_record_hashes" if record_status == "verified" else "unknown")


def _verdict(status: VerdictStatus, reason: str) -> CapabilityVerdict:
    return CapabilityVerdict(status, (reason,))


def _storage(name: str, path: str | Path, handlers, durability: Durability | None) -> StorageIdentity:
    started = _now()
    resolved = str(Path(path).resolve())
    facts: dict[str, Any] = {}
    tables: tuple[str, ...] = ()
    truncated = False
    summary_time = None
    summary = _verdict("not_checked", "catalog_not_checked")
    schemas: dict[str, int | str] = {}
    integrity = "unknown"
    bindings = "not_checked" if handlers is None else "unknown"
    exists: bool | None = None
    reasons: tuple[str, ...] = ()
    try:
        exists = Path(path).exists()
        facts = inspect_storage(path, handlers=handlers)
        exists = facts["exists"]
        schemas = {key.removesuffix("_schema"): value for key, value in facts.items() if key.endswith("_schema")}
        if not exists:
            status = "missing"
            read = execute = resume = _verdict("unsupported", "storage_missing")
            summary = _verdict("unsupported", "storage_missing")
        else:
            integrity = "failed" if any(item["component"] == "sqlite" for item in facts["issues"]) else "ok"
            unsupported = any(value == "unsupported" for value in schemas.values())
            recognized = any(isinstance(value, int) for value in schemas.values())
            status = "damaged" if integrity == "failed" else "unsupported" if unsupported or not recognized else "recognized"
            if status != "recognized":
                read = execute = resume = _verdict("unsupported", "storage_" + status)
            else:
                read = _verdict("supported", "recognized_schema")
                execution_store = any(isinstance(schemas.get(component), int)
                    for component in ("kernel", "orchestrator"))
                bindings = "checked" if handlers is not None and execution_store else "not_checked"
                if not execution_store:
                    # A journal/inbox schema says nothing about the owning
                    # execution store, handler eligibility or recovery authority.
                    execute = _verdict("not_applicable", "auxiliary_storage_only")
                    resume = _verdict("unknown", "owning_execution_store_not_checked")
                elif facts["issues"]:
                    execute = resume = _verdict("unsupported", "storage_or_binding_incompatible")
                else:
                    execute = _verdict("supported", "recognized_schema")
                    resume = _verdict("unknown", "bindings_not_checked") if handlers is None else _verdict("supported", "schema_and_bindings_checked")
            # Only generic SQLite catalog metadata is supported for arbitrary old schemas.
            # No legacy application rows are interpreted or promoted to execution authority.
            if integrity == "ok":
                try:
                    with _read_only(path) as connection:
                        connection.execute("BEGIN")
                        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 101").fetchall()
                        tables = tuple(row[0] for row in rows[:100])
                        truncated = len(rows) > 100
                    summary_time = _now()
                    summary = _verdict("supported", "sqlite_catalog_only")
                except (OSError, sqlite3.DatabaseError):
                    summary = _verdict("unknown", "catalog_snapshot_unavailable")
    except FileNotFoundError:
        status, exists = "missing", False
        read = execute = resume = summary = _verdict("unsupported", "storage_missing")
    except sqlite3.DatabaseError as error:
        # I/O, lock and permission failures do not prove physical corruption.
        code = getattr(error, "sqlite_errorcode", None)
        if code is not None:
            damaged = (code & 0xff) in (11, 26)  # SQLITE_CORRUPT, SQLITE_NOTADB
        else:
            # Python 3.10 does not expose SQLite result codes on exceptions.
            # Match only SQLite's explicit corruption messages, not arbitrary
            # database errors such as locks, permissions or failed reads.
            damaged = str(error) in ("database disk image is malformed", "file is not a database")
        status = "damaged" if damaged else "unknown"
        integrity = "failed" if damaged else "unknown"
        read = execute = resume = _verdict("unsupported" if damaged else "unknown", "storage_" + status)
        reasons = ("sqlite_read_failed",)
    except (OSError, ValueError, TypeError, KeyError) as error:
        status = "unknown"
        read = execute = resume = _verdict("unknown", "storage_inspection_failed")
        reasons = ("storage_inspection_failed", type(error).__name__)
    return StorageIdentity(name, resolved, started, _now(), status, exists, schemas, integrity,
        bindings, facts, DurabilityObservation(durability, facts.get("journal_mode")),
        read, execute, resume, summary, tables, truncated, summary_time, reasons)


def _aggregate(storages: tuple[StorageIdentity, ...], capability: str) -> CapabilityVerdict:
    if not storages:
        return _verdict("not_checked", "storage_not_supplied")
    values = [getattr(storage, capability) for storage in storages]
    for status in ("unsupported", "unknown", "not_checked", "not_applicable"):
        if any(value.status == status for value in values):
            return CapabilityVerdict(status, tuple(dict.fromkeys(reason for value in values
                if value.status == status for reason in value.reasons)))
    return _verdict("supported", "all_supplied_storage_checks_passed")


def runtime_identity(path: str | Path | None = None, *, handlers: Mapping[Any, Handler] | None = None,
                     durability: Durability | None = None,
                     component_paths: Mapping[str, str | Path] | None = None) -> RuntimeIdentityReport:
    """Describe imported source, registry and storage without initializing writers.

    ``path`` names the main store; ``component_paths`` adds independently observed
    inbox/journal stores. Verdicts cover only supplied paths, not a particular Run
    or all external resources. ``read`` means current SDK schema reader support;
    legacy SQLite catalog summaries have their own ``summary`` verdict. ``execute``
    covers execution-store compatibility; pure auxiliary journals/inboxes do not
    establish execution or recovery support. ``resume`` additionally requires checked bindings.
    Neither verdict proves an execution is claimable or authorizes bypassing CAS.
    ``durability`` is a caller declaration, never another connection's observation.
    Source hashes cover .py files on disk and wheel RECORD is unsigned evidence,
    not authentication or verification of already loaded bytecode.
    """
    started = _now()
    if durability is not None:
        validate_durability(durability)
    normalized = None if handlers is None else normalize_handlers(handlers)
    revision = None if normalized is None else registry_revision(normalized)
    bindings = () if normalized is None else tuple(HandlerBindingIdentity(key[0], key[1],
        handler_revision(normalized, *key)) for key in sorted(normalized))
    paths = dict(component_paths or {})
    if path is not None:
        if "main" in paths:
            raise ValueError("component_paths must not contain 'main' when path is supplied")
        paths = {"main": path, **paths}
    if any(not isinstance(name, str) or not name for name in paths):
        raise ValueError("component path names must be non-empty strings")
    storages = tuple(_storage(name, item, normalized, durability) for name, item in paths.items())
    module = _source_identity()
    execute, resume = _aggregate(storages, "execute"), _aggregate(storages, "resume")
    identity_errors = tuple(reason for condition, reason in (
        (module.version_agreement == "mismatch", "distribution_source_version_mismatch"),
        (module.distribution_record == "mismatch", "distribution_source_files_mismatch")) if condition)
    if identity_errors:
        # Read support is independent of deployment identity. Do not issue a
        # positive deployment verdict when installed and imported artifacts differ.
        execute = CapabilityVerdict("unsupported", tuple(dict.fromkeys(identity_errors + execute.reasons)))
        resume = CapabilityVerdict("unsupported", tuple(dict.fromkeys(identity_errors + resume.reasons)))
    return RuntimeIdentityReport(started, _now(), module,
        {"execution_command": SCHEMA_VERSION, "execution_result": SCHEMA_VERSION,
         "handler_registry": 2, "handler_binding": 1, "runtime_identity": 1},
        revision, bindings, storages, _aggregate(storages, "read"), execute, resume)


__all__ = ["runtime_identity", "RuntimeIdentityReport", "ModuleIdentity", "StorageIdentity",
           "CapabilityVerdict", "HandlerBindingIdentity", "DurabilityObservation", "VerdictStatus"]
