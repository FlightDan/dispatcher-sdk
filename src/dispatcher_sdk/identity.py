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
from typing import Any, Callable, Literal, Mapping

from . import _version
from ._inspection import InspectionBudget, InspectionBudgetExceeded
from .durability import Durability, validate_durability
from .execution_kernel._registry import Handler, handler_revision, normalize_handlers, registry_revision
from .execution_kernel.contracts import SCHEMA_VERSION
from .storage import StorageInspectionCheck, _inspect_storage, _read_only

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
    integrity: Literal["ok", "failed", "unknown", "not_checked"]
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
    requested_check: StorageInspectionCheck = "full"
    actual_scope: tuple[str, ...] = ("module",)
    complete: bool = True
    stopped_reason: str | None = None
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report (no callable or connection objects)."""
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unknown_module_identity() -> ModuleIdentity:
    root = Path(__file__).resolve().parent
    return ModuleIdentity(None, str(root / "__init__.py"), None, "unknown", None,
                          "unknown", "unknown", "unknown")


def _source_identity(budget: InspectionBudget | None = None) -> ModuleIdentity:
    if budget is not None:
        budget.check()
    root = Path(__file__).resolve().parent
    try:
        distribution = metadata.distribution("dispatcher-sdk")
        installed_version = distribution.version
    except metadata.PackageNotFoundError:
        distribution = None
        installed_version = None
    if budget is not None:
        budget.check()
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
            if budget is not None:
                budget.check()
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
            if budget is not None:
                budget.check()
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


def _storage(name: str, path: str | Path, handlers, durability: Durability | None,
             check: StorageInspectionCheck, budget: InspectionBudget,
             bindings_requested: bool) -> StorageIdentity:
    started = _now()
    resolved = str(Path(path).resolve())
    facts: dict[str, Any] = {}
    tables: tuple[str, ...] = ()
    truncated = False
    summary_time = None
    summary = _verdict("not_checked", "catalog_not_checked")
    schemas: dict[str, int | str] = {}
    integrity = "not_checked" if check != "full" else "unknown"
    bindings = "unknown" if bindings_requested else "not_checked"
    exists: bool | None = None
    reasons: tuple[str, ...] = ()
    try:
        exists = Path(path).exists()
        facts = _inspect_storage(path, handlers=handlers, check=check, budget=budget,
                                 snapshot_name=name)
        exists = facts["exists"]
        schemas = {key.removesuffix("_schema"): value for key, value in facts.items() if key.endswith("_schema")}
        if not exists:
            status = "missing"
            read = execute = resume = _verdict("unsupported", "storage_missing")
            summary = _verdict("unsupported", "storage_missing")
        else:
            integrity_status = facts.get("checks", {}).get("integrity", "unknown")
            integrity = ("failed" if integrity_status == "failed" else "ok" if integrity_status == "ok"
                         else "not_checked" if integrity_status == "not_checked" else "unknown")
            unsupported = any(value == "unsupported" for value in schemas.values())
            recognized = any(isinstance(value, int) for value in schemas.values())
            schema_status = facts.get("checks", {}).get("schema", "unknown")
            status = ("damaged" if integrity == "failed" else "unknown"
                      if schema_status == "unknown" else "unsupported"
                      if unsupported or not recognized else "recognized")
            if status != "recognized":
                verdict = "unknown" if status == "unknown" else "unsupported"
                read = execute = resume = _verdict(verdict, "storage_" + status)
            else:
                read = _verdict("supported", "recognized_schema")
                execution_store = any(isinstance(schemas.get(component), int)
                    for component in ("kernel", "orchestrator"))
                binding_status = facts.get("checks", {}).get("bindings", "not_checked")
                bindings = ("checked" if binding_status == "checked" and execution_store else
                            "unknown" if binding_status == "unknown" and execution_store else "not_checked")
                if not execution_store:
                    # A journal/inbox schema says nothing about the owning
                    # execution store, handler eligibility or recovery authority.
                    execute = _verdict("not_applicable", "auxiliary_storage_only")
                    resume = _verdict("unknown", "owning_execution_store_not_checked")
                elif any(item["component"] != "sqlite" for item in facts["issues"]):
                    execute = resume = _verdict("unsupported", "storage_or_binding_incompatible")
                else:
                    execute = _verdict("supported", "recognized_schema")
                    resume = (_verdict("supported", "schema_and_bindings_checked")
                              if bindings == "checked" else
                              _verdict("unknown", "binding_check_incomplete")
                              if bindings == "unknown" else
                              _verdict("unknown", "bindings_not_checked"))
            # Only generic SQLite catalog metadata is supported for arbitrary old schemas.
            # No legacy application rows are interpreted or promoted to execution authority.
            if integrity != "failed" and facts.get("complete", True):
                try:
                    budget.check()
                    with _read_only(path, timeout=budget.sqlite_timeout_seconds) as connection:
                        budget.install(connection)
                        connection.execute("BEGIN")
                        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 101").fetchall()
                        tables = tuple(row[0] for row in rows[:100])
                        truncated = len(rows) > 100
                    summary_time = _now()
                    summary = _verdict("supported", "sqlite_catalog_only")
                except InspectionBudgetExceeded:
                    facts["complete"] = False
                    facts["stopped_reason"] = budget.stopped_reason or "timeout"
                    facts["elapsed_seconds"] = budget.elapsed_seconds
                    if not facts["issues"]:
                        facts["compatible"] = None
                    summary = _verdict("unknown", "catalog_snapshot_incomplete")
                except (OSError, sqlite3.DatabaseError) as error:
                    if isinstance(error, sqlite3.DatabaseError) and budget.interrupted(error):
                        facts["complete"] = False
                        facts["stopped_reason"] = budget.stopped_reason or "timeout"
                        facts["elapsed_seconds"] = budget.elapsed_seconds
                        if not facts["issues"]:
                            facts["compatible"] = None
                        summary = _verdict("unknown", "catalog_snapshot_incomplete")
                    else:
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
                     component_paths: Mapping[str, str | Path] | None = None,
                     check: StorageInspectionCheck = "full",
                     timeout_seconds: float | None = None,
                     progress: Callable[[dict[str, Any]], None] | None = None) -> RuntimeIdentityReport:
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
    if check not in ("schema", "bindings", "full"):
        raise ValueError("check must be 'schema', 'bindings', or 'full'")
    budget = InspectionBudget(timeout_seconds, progress)
    if durability is not None:
        validate_durability(durability)
    paths = dict(component_paths or {})
    if path is not None:
        if "main" in paths:
            raise ValueError("component_paths must not contain 'main' when path is supplied")
        paths = {"main": path, **paths}
    if any(not isinstance(name, str) or not name for name in paths):
        raise ValueError("component path names must be non-empty strings")
    budget.emit("module", "started")
    module_complete = True
    try:
        module = _source_identity(budget)
    except InspectionBudgetExceeded:
        module = _unknown_module_identity()
        module_complete = False
        budget.emit("module", "stopped", reason=budget.stopped_reason or "timeout")
    else:
        budget.emit("module", "completed")
    normalized = None
    revision = None
    bindings: tuple[HandlerBindingIdentity, ...] = ()
    registry_complete = False
    if module_complete:
        try:
            budget.emit("registry", "started")
            budget.check()
            normalized = None if handlers is None else normalize_handlers(handlers)
            budget.check()
            revision = None if normalized is None else registry_revision(normalized)
            budget.check()
            binding_items = []
            if normalized is not None:
                for key in sorted(normalized):
                    budget.check()
                    binding_items.append(HandlerBindingIdentity(
                        key[0], key[1], handler_revision(normalized, *key)))
                    budget.check()
            bindings = tuple(binding_items)
            registry_complete = True
            budget.emit("registry", "completed")
        except InspectionBudgetExceeded:
            normalized = None
            revision = None
            bindings = ()
            budget.emit("registry", "stopped", reason=budget.stopped_reason or "timeout")
    storages = tuple(_storage(name, item, normalized, durability, check, budget,
                              handlers is not None)
                     for name, item in paths.items())
    execute, resume = _aggregate(storages, "execute"), _aggregate(storages, "resume")
    identity_errors = tuple(reason for condition, reason in (
        (module.version_agreement == "mismatch", "distribution_source_version_mismatch"),
        (module.distribution_record == "mismatch", "distribution_source_files_mismatch")) if condition)
    if identity_errors:
        # Read support is independent of deployment identity. Do not issue a
        # positive deployment verdict when installed and imported artifacts differ.
        execute = CapabilityVerdict("unsupported", tuple(dict.fromkeys(identity_errors + execute.reasons)))
        resume = CapabilityVerdict("unsupported", tuple(dict.fromkeys(identity_errors + resume.reasons)))
    actual_scope = (("module", "registry") if registry_complete else
                    ("module",) if module_complete else ()) + tuple(
        f"{storage.name}:{scope}" for storage in storages
        for scope in storage.facts.get("actual_scope", ()))
    complete = (module_complete and registry_complete
                and all(storage.facts.get("complete", True) for storage in storages))
    stopped_reason = next((storage.facts.get("stopped_reason") for storage in storages
                           if storage.facts.get("stopped_reason")),
                          budget.stopped_reason if not complete else None)
    return RuntimeIdentityReport(started, _now(), module,
        {"execution_command": SCHEMA_VERSION, "execution_result": SCHEMA_VERSION,
         "handler_registry": 2, "handler_binding": 1, "runtime_identity": 1},
        revision, bindings, storages, _aggregate(storages, "read"), execute, resume,
        requested_check=check, actual_scope=actual_scope, complete=complete,
        stopped_reason=stopped_reason, elapsed_seconds=budget.elapsed_seconds)


__all__ = ["runtime_identity", "RuntimeIdentityReport", "ModuleIdentity", "StorageIdentity",
           "CapabilityVerdict", "HandlerBindingIdentity", "DurabilityObservation", "VerdictStatus"]
