"""Bounded, read-only lookup of an execution's accepted application origin."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Literal

from ..content import ContentIntegrityError, ContentReadBudget, ContentSizeLimitError, decode_value
from ..execution_kernel import ExecutionCommandV2
from ..storage import _read_only


DEFAULT_MAX_PAYLOAD_BYTES = 1024 * 1024
DEFAULT_MAX_QUERY_STEPS = 100_000
DEFAULT_TIMEOUT = 5.0

OriginStatus = Literal["found", "not_found", "incomplete"]
LookupKind = Literal["execution_id", "result_id"]


@dataclass(frozen=True)
class ExecutionHandlerBinding:
    """The immutable handler binding accepted with the original command."""

    handler_id: str
    handler_contract_version: int
    registry_revision: str


@dataclass(frozen=True)
class ExecutionOriginReport:
    """JSON-safe evidence connecting an execution or result to its origin.

    ``source_scope`` is deliberately limited to the supplied store.  A
    ``not_found`` report therefore says nothing about other databases.  The
    handler binding is persisted command evidence, not a claim that a matching
    deployment is currently available.
    """

    status: OriginStatus
    complete: bool
    reason_codes: tuple[str, ...]
    source_path: str
    source_scope: Literal["supplied_store"]
    store_id: str | None
    store_incarnation: str | None
    schema_version: int | None
    lookup_kind: LookupKind
    lookup_id: str
    execution_id: str | None
    result_id: str | None
    run_id: str | None
    previous_run_id: str | None
    next_run_id: str | None
    task_id: str | None
    application_attempt: int | None
    generation: int | None
    task: dict[str, Any] | None
    attempt: dict[str, Any] | None
    command: dict[str, Any] | None
    handler_binding: ExecutionHandlerBinding | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class _PayloadLimit(Exception):
    pass


class _InspectionTimeout(Exception):
    pass


class _StoredPayload(Exception):
    pass


_REQUIRED_COLUMNS = {
    "sdk_schema_meta": {"component", "version"},
    "sdk_storage_identity": {"singleton", "store_id", "incarnation"},
    "sdk_results": {"result_id", "execution_id"},
    "sdk_executions": {
        "execution_id", "run_id", "task_id", "attempt", "generation", "command"
    },
    "sdk_run_items": {"run_id", "section", "item_key", "value"},
    "sdk_run_links": {"previous_run_id", "next_run_id"},
    "sdk_runs": {"run_id"},
    "sdk_run_history": {"run_id", "section", "item_key", "revision", "value"},
    "sdk_expired_revisions": {"run_id", "revision"},
    "sdk_disposed_runs": {"run_id"},
    "sdk_content_objects": {"digest", "encoded", "logical_bytes"},
}


def _positive_integer(value: Any, name: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def _positive_timeout(value: Any) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be positive and finite")
    return float(value)


def _identity(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _index_for(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    *,
    unique: bool = False,
) -> str:
    """Return an exact declared index and prevent accidental table scans."""
    for row in connection.execute(f"PRAGMA index_list({_quoted(table)})"):
        name = str(row[1])
        if bool(row[4]):  # A partial index cannot cover arbitrary identities.
            continue
        if unique and not bool(row[2]):
            continue
        actual = tuple(
            str(item[2])
            for item in connection.execute(f"PRAGMA index_info({_quoted(name)})")
        )
        if actual == columns:
            return _quoted(name)
    raise ValueError(f"required index on {table}{columns!r} is missing")


def _validate_schema(connection: sqlite3.Connection) -> dict[tuple[str, tuple[str, ...]], str]:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name GLOB 'sdk_*'"
        )
    }
    if not _REQUIRED_COLUMNS.keys() <= tables:
        raise ValueError("orchestrator schema is missing required tables")
    marker = connection.execute(
        "SELECT component,version FROM sdk_schema_meta"
    ).fetchall()
    if len(marker) != 1 or tuple(marker[0]) != ("orchestrator", 3):
        raise ValueError("unsupported orchestrator schema")
    for table, required in _REQUIRED_COLUMNS.items():
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({_quoted(table)})")
        }
        if not required <= columns:
            raise ValueError(f"{table} is missing required columns")
    specifications = (
        ("sdk_results", ("result_id",), True),
        ("sdk_results", ("execution_id",), True),
        ("sdk_executions", ("execution_id",), True),
        ("sdk_run_items", ("run_id", "section", "item_key"), True),
        ("sdk_run_links", ("previous_run_id",), True),
        ("sdk_run_links", ("next_run_id",), True),
        ("sdk_runs", ("run_id",), True),
        ("sdk_run_history", ("run_id", "section", "item_key", "revision"), True),
        ("sdk_expired_revisions", ("run_id", "revision"), True),
        ("sdk_disposed_runs", ("run_id",), True),
        ("sdk_content_objects", ("digest",), True),
    )
    return {
        (table, columns): _index_for(connection, table, columns, unique=unique)
        for table, columns, unique in specifications
    }


def _canonical_bytes(value: Any) -> int:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
    except (RecursionError, TypeError, ValueError) as exc:
        raise _StoredPayload from exc
    return len(encoded.encode("utf-8"))


def _decode_payload(
    connection: sqlite3.Connection,
    encoded: str,
    remaining: int,
    read_budget: ContentReadBudget,
) -> tuple[Any, int]:
    if remaining <= 0:
        raise _PayloadLimit
    try:
        value = decode_value(
            connection,
            encoded,
            max_logical_bytes=remaining,
            max_encoded_bytes=remaining,
            read_budget=read_budget,
        )
    except ContentSizeLimitError as exc:
        raise _PayloadLimit from exc
    except ContentIntegrityError as exc:
        raise _StoredPayload from exc
    except (TypeError, ValueError) as exc:
        raise _StoredPayload from exc
    size = _canonical_bytes(value)
    if size > remaining:
        raise _PayloadLimit
    return value, size


def _empty_report(
    path: Path,
    lookup_kind: LookupKind,
    lookup_id: str,
    *,
    status: OriginStatus,
    reason_codes: tuple[str, ...],
    schema_version: int | None = None,
    store_id: str | None = None,
    store_incarnation: str | None = None,
    execution_id: str | None = None,
    result_id: str | None = None,
) -> ExecutionOriginReport:
    return ExecutionOriginReport(
        status=status,
        complete=status == "not_found",
        reason_codes=reason_codes,
        source_path=str(path),
        source_scope="supplied_store",
        store_id=store_id,
        store_incarnation=store_incarnation,
        schema_version=schema_version,
        lookup_kind=lookup_kind,
        lookup_id=lookup_id,
        execution_id=execution_id,
        result_id=result_id,
        run_id=None,
        previous_run_id=None,
        next_run_id=None,
        task_id=None,
        application_attempt=None,
        generation=None,
        task=None,
        attempt=None,
        command=None,
        handler_binding=None,
    )


def _missing_projection_reason(
    connection: sqlite3.Connection,
    indexes: dict[tuple[str, tuple[str, ...]], str],
    run_id: str,
    section: str,
    item_key: str,
) -> str:
    history_index = indexes[(
        "sdk_run_history", ("run_id", "section", "item_key", "revision")
    )]
    historical = connection.execute(
        f"SELECT 1 FROM sdk_run_history INDEXED BY {history_index} "
        "WHERE run_id=? AND section=? AND item_key=? LIMIT 1",
        (run_id, section, item_key),
    ).fetchone()
    if historical is not None:
        return f"{section}_projection_incomplete"
    expired_index = indexes[("sdk_expired_revisions", ("run_id", "revision"))]
    expired = connection.execute(
        f"SELECT 1 FROM sdk_expired_revisions INDEXED BY {expired_index} "
        "WHERE run_id=? LIMIT 1",
        (run_id,),
    ).fetchone()
    return f"{section}_evidence_pruned" if expired is not None else f"{section}_evidence_unknown"


def inspect_execution_origin(
    path: str | os.PathLike[str],
    *,
    execution_id: str | None = None,
    result_id: str | None = None,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    max_query_steps: int = DEFAULT_MAX_QUERY_STEPS,
    timeout: float = DEFAULT_TIMEOUT,
) -> ExecutionOriginReport:
    """Locate one execution's original Run, task, attempt and frozen command.

    Exactly one identity is required.  All lookups are point queries through
    declared indexes in the supplied schema-v3 store.  This function does not
    scan directories, follow external provenance, initialize a writer, or load
    a complete Run/history.  The SQL budget is cumulative across schema checks
    and lookup queries; the payload budget applies both to encoded rows before
    retrieval and to their total decoded logical JSON.
    """
    if (execution_id is None) == (result_id is None):
        raise ValueError("provide exactly one of execution_id or result_id")
    lookup_kind: LookupKind = "execution_id" if execution_id is not None else "result_id"
    lookup_id = _identity(execution_id if execution_id is not None else result_id, lookup_kind)
    payload_limit = _positive_integer(max_payload_bytes, "max_payload_bytes", 128 * 1024 * 1024)
    step_limit = _positive_integer(max_query_steps, "max_query_steps", 100_000_000)
    timeout_seconds = _positive_timeout(timeout)
    source = Path(path).expanduser().resolve()
    if str(path) == ":memory:" or not source.is_file():
        return _empty_report(
            source, lookup_kind, lookup_id, status="incomplete",
            reason_codes=("source_store_not_found",),
            execution_id=execution_id, result_id=result_id,
        )

    deadline = time.monotonic() + timeout_seconds
    progress = {"steps": 0, "reason": None}

    def check_deadline() -> None:
        if time.monotonic() > deadline:
            progress["reason"] = "inspection_timeout"
            raise _InspectionTimeout

    def check_budget() -> int:
        progress["steps"] += 1
        if progress["steps"] > step_limit:
            progress["reason"] = "query_step_budget_exceeded"
            return 1
        if time.monotonic() > deadline:
            progress["reason"] = "inspection_timeout"
            return 1
        return 0

    connection: sqlite3.Connection | None = None
    store_id = store_incarnation = None
    schema_version = None
    try:
        with _read_only(source, timeout=timeout_seconds) as connection:
            connection.execute(f"PRAGMA busy_timeout={max(1, int(timeout_seconds * 1000))}")
            connection.set_progress_handler(check_budget, 1)
            connection.execute("BEGIN")
            try:
                indexes = _validate_schema(connection)
                schema_version = 3
            except ValueError:
                return _empty_report(
                    source, lookup_kind, lookup_id, status="incomplete",
                    reason_codes=("unsupported_or_incomplete_schema",),
                    execution_id=execution_id, result_id=result_id,
                )
            check_deadline()
            identity = connection.execute(
                "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
            ).fetchone()
            if (
                identity is None
                or type(identity[0]) is not str or not identity[0]
                or type(identity[1]) is not str or not identity[1]
            ):
                return _empty_report(
                    source, lookup_kind, lookup_id, status="incomplete",
                    reason_codes=("source_identity_missing",), schema_version=3,
                    execution_id=execution_id, result_id=result_id,
                )
            store_id, store_incarnation = identity[0], identity[1]

            result_index = indexes[("sdk_results", ("result_id",))]
            result_execution_index = indexes[("sdk_results", ("execution_id",))]
            if lookup_kind == "result_id":
                result_row = connection.execute(
                    f"SELECT result_id,execution_id FROM sdk_results INDEXED BY {result_index} "
                    "WHERE result_id=?",
                    (lookup_id,),
                ).fetchone()
                if result_row is None:
                    return _empty_report(
                        source, lookup_kind, lookup_id, status="not_found",
                        reason_codes=("result_not_found_in_supplied_store",),
                        schema_version=3, store_id=store_id,
                        store_incarnation=store_incarnation, result_id=lookup_id,
                    )
                result_id = str(result_row[0])
                execution_id = str(result_row[1])
            else:
                result_row = connection.execute(
                    f"SELECT result_id,execution_id FROM sdk_results "
                    f"INDEXED BY {result_execution_index} WHERE execution_id=?",
                    (lookup_id,),
                ).fetchone()
                if result_row is not None:
                    result_id = str(result_row[0])

            execution_index = indexes[("sdk_executions", ("execution_id",))]
            length_row = connection.execute(
                f"SELECT run_id,task_id,attempt,generation,"
                "length(CAST(command AS BLOB)) FROM sdk_executions "
                f"INDEXED BY {execution_index} WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
            if length_row is None:
                status: OriginStatus = "incomplete" if result_row is not None else "not_found"
                reason = (
                    "execution_registration_missing"
                    if result_row is not None
                    else "execution_not_found_in_supplied_store"
                )
                return _empty_report(
                    source, lookup_kind, lookup_id, status=status,
                    reason_codes=(reason,), schema_version=3, store_id=store_id,
                    store_incarnation=store_incarnation,
                    execution_id=execution_id, result_id=result_id,
                )
            run_id, task_id, application_attempt, generation, command_bytes = tuple(length_row)
            if (
                type(run_id) is not str or not run_id
                or type(task_id) is not str or not task_id
                or type(application_attempt) is not int or application_attempt < 0
                or type(generation) is not int or generation < 0
                or type(command_bytes) is not int or command_bytes < 0
            ):
                return _empty_report(
                    source, lookup_kind, lookup_id, status="incomplete",
                    reason_codes=("execution_registration_invalid",), schema_version=3,
                    store_id=store_id, store_incarnation=store_incarnation,
                    execution_id=execution_id, result_id=result_id,
                )

            disposed_index = indexes[("sdk_disposed_runs", ("run_id",))]
            if connection.execute(
                f"SELECT 1 FROM sdk_disposed_runs INDEXED BY {disposed_index} WHERE run_id=?",
                (run_id,),
            ).fetchone() is not None:
                partial = _empty_report(
                    source, lookup_kind, lookup_id, status="incomplete",
                    reason_codes=("origin_run_disposed",), schema_version=3,
                    store_id=store_id, store_incarnation=store_incarnation,
                    execution_id=execution_id, result_id=result_id,
                )
                return replace(
                    partial, run_id=run_id, task_id=task_id,
                    application_attempt=application_attempt, generation=generation,
                )
            run_index = indexes[("sdk_runs", ("run_id",))]
            if connection.execute(
                f"SELECT 1 FROM sdk_runs INDEXED BY {run_index} WHERE run_id=?", (run_id,)
            ).fetchone() is None:
                partial = _empty_report(
                    source, lookup_kind, lookup_id, status="incomplete",
                    reason_codes=("origin_run_unknown",), schema_version=3,
                    store_id=store_id, store_incarnation=store_incarnation,
                    execution_id=execution_id, result_id=result_id,
                )
                return replace(
                    partial, run_id=run_id, task_id=task_id,
                    application_attempt=application_attempt, generation=generation,
                )

            item_index = indexes[("sdk_run_items", ("run_id", "section", "item_key"))]
            attempt_key = json.dumps(
                [task_id, application_attempt], separators=(",", ":"), ensure_ascii=False
            )
            task_length = connection.execute(
                f"SELECT length(CAST(value AS BLOB)) FROM sdk_run_items "
                f"INDEXED BY {item_index} WHERE run_id=? AND section='task' AND item_key=?",
                (run_id, task_id),
            ).fetchone()
            attempt_length = connection.execute(
                f"SELECT length(CAST(value AS BLOB)) FROM sdk_run_items "
                f"INDEXED BY {item_index} WHERE run_id=? AND section='attempt' AND item_key=?",
                (run_id, attempt_key),
            ).fetchone()
            missing = []
            if task_length is None:
                missing.append(_missing_projection_reason(
                    connection, indexes, run_id, "task", task_id
                ))
            if attempt_length is None:
                missing.append(_missing_projection_reason(
                    connection, indexes, run_id, "attempt", attempt_key
                ))
            if missing:
                partial = _empty_report(
                    source, lookup_kind, lookup_id, status="incomplete",
                    reason_codes=tuple(missing), schema_version=3, store_id=store_id,
                    store_incarnation=store_incarnation,
                    execution_id=execution_id, result_id=result_id,
                )
                return replace(
                    partial, run_id=run_id, task_id=task_id,
                    application_attempt=application_attempt, generation=generation,
                )
            stored_bytes = command_bytes + task_length[0] + attempt_length[0]
            if stored_bytes > payload_limit:
                raise _PayloadLimit

            read_budget = ContentReadBudget(payload_limit)
            command_row = connection.execute(
                f"SELECT command FROM sdk_executions INDEXED BY {execution_index} "
                "WHERE execution_id=? AND length(CAST(command AS BLOB))<=?",
                (execution_id, payload_limit),
            ).fetchone()
            if command_row is None:
                raise _PayloadLimit
            logical_remaining = payload_limit
            command_value, size = _decode_payload(connection, command_row[0], logical_remaining, read_budget)
            check_deadline()
            logical_remaining -= size
            if task_length[0] > read_budget.remaining:
                raise _PayloadLimit
            task_row = connection.execute(
                f"SELECT value FROM sdk_run_items INDEXED BY {item_index} "
                "WHERE run_id=? AND section='task' AND item_key=? "
                "AND length(CAST(value AS BLOB))<=?",
                (run_id, task_id, payload_limit),
            ).fetchone()
            if task_row is None:
                raise _PayloadLimit
            task_value, size = _decode_payload(connection, task_row[0], logical_remaining, read_budget)
            check_deadline()
            logical_remaining -= size
            if attempt_length[0] > read_budget.remaining:
                raise _PayloadLimit
            attempt_row = connection.execute(
                f"SELECT value FROM sdk_run_items INDEXED BY {item_index} "
                "WHERE run_id=? AND section='attempt' AND item_key=? "
                "AND length(CAST(value AS BLOB))<=?",
                (run_id, attempt_key, payload_limit),
            ).fetchone()
            if attempt_row is None:
                raise _PayloadLimit
            attempt_value, _ = _decode_payload(connection, attempt_row[0], logical_remaining, read_budget)
            check_deadline()
            if type(command_value) is not dict or type(task_value) is not dict or type(attempt_value) is not dict:
                raise _StoredPayload
            try:
                parsed = ExecutionCommandV2.from_dict(command_value).to_dict()
            except (TypeError, ValueError, KeyError) as exc:
                raise _StoredPayload from exc
            if parsed["execution_id"] != execution_id:
                raise _StoredPayload
            attempt_command = attempt_value.get("command")
            if type(attempt_command) is not dict or attempt_command != parsed:
                raise _StoredPayload
            attempt_generation = attempt_value.get("generation", 0)
            if attempt_generation != generation:
                partial_reason = ("attempt_generation_mismatch",)
            else:
                partial_reason = ()
            task_identity = task_value.get("task_id")
            if type(task_identity) is not str or task_identity != task_id:
                partial_reason += ("task_identity_mismatch",)

            previous_index = indexes[("sdk_run_links", ("next_run_id",))]
            next_index = indexes[("sdk_run_links", ("previous_run_id",))]
            previous = connection.execute(
                f"SELECT previous_run_id FROM sdk_run_links INDEXED BY {previous_index} "
                "WHERE next_run_id=?", (run_id,),
            ).fetchone()
            following = connection.execute(
                f"SELECT next_run_id FROM sdk_run_links INDEXED BY {next_index} "
                "WHERE previous_run_id=?", (run_id,),
            ).fetchone()
            if any(row is not None and (type(row[0]) is not str or not row[0].strip())
                   for row in (previous, following)):
                raise _StoredPayload
            binding = ExecutionHandlerBinding(
                handler_id=parsed["handler_id"],
                handler_contract_version=parsed["handler_contract_version"],
                registry_revision=parsed["registry_revision"],
            )
            status = "incomplete" if partial_reason else "found"
            return ExecutionOriginReport(
                status=status,
                complete=not partial_reason,
                reason_codes=partial_reason,
                source_path=str(source),
                source_scope="supplied_store",
                store_id=store_id,
                store_incarnation=store_incarnation,
                schema_version=3,
                lookup_kind=lookup_kind,
                lookup_id=lookup_id,
                execution_id=execution_id,
                result_id=result_id,
                run_id=run_id,
                previous_run_id=None if previous is None else previous[0],
                next_run_id=None if following is None else following[0],
                task_id=task_id,
                application_attempt=application_attempt,
                generation=generation,
                task=task_value,
                attempt={key: value for key, value in attempt_value.items() if key != "command"},
                command=parsed,
                handler_binding=binding,
            )
    except _InspectionTimeout:
        return _empty_report(
            source, lookup_kind, lookup_id, status="incomplete",
            reason_codes=("inspection_timeout",), schema_version=schema_version,
            store_id=store_id, store_incarnation=store_incarnation,
            execution_id=execution_id, result_id=result_id,
        )
    except _PayloadLimit:
        return _empty_report(
            source, lookup_kind, lookup_id, status="incomplete",
            reason_codes=("payload_budget_exceeded",), schema_version=schema_version,
            store_id=store_id, store_incarnation=store_incarnation,
            execution_id=execution_id, result_id=result_id,
        )
    except _StoredPayload:
        return _empty_report(
            source, lookup_kind, lookup_id, status="incomplete",
            reason_codes=("stored_origin_payload_invalid",), schema_version=schema_version,
            store_id=store_id, store_incarnation=store_incarnation,
            execution_id=execution_id, result_id=result_id,
        )
    except sqlite3.OperationalError as exc:
        if progress["reason"] is not None or "interrupted" in str(exc).lower():
            reason = progress["reason"] or "query_budget_exceeded"
        elif "locked" in str(exc).lower() or "busy" in str(exc).lower():
            reason = "source_store_busy"
        else:
            reason = "source_store_unavailable"
        return _empty_report(
            source, lookup_kind, lookup_id, status="incomplete",
            reason_codes=(reason,), schema_version=schema_version,
            store_id=store_id, store_incarnation=store_incarnation,
            execution_id=execution_id, result_id=result_id,
        )
    except (OSError, sqlite3.DatabaseError):
        return _empty_report(
            source, lookup_kind, lookup_id, status="incomplete",
            reason_codes=("source_store_unavailable",), schema_version=schema_version,
            store_id=store_id, store_incarnation=store_incarnation,
            execution_id=execution_id, result_id=result_id,
        )
    finally:
        if connection is not None:
            try:
                connection.set_progress_handler(None, 0)
            except sqlite3.ProgrammingError:
                # The read-only context closes before a return reaches this
                # outer cleanup.  There is no live handler in that case.
                pass


__all__ = [
    "ExecutionHandlerBinding", "ExecutionOriginReport", "inspect_execution_origin",
]
