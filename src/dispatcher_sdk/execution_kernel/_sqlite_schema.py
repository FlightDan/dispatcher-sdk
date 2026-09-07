"""Exact v2 SQLite schema validation and post-bootstrap authorization."""

from __future__ import annotations

import re
import math
import sqlite3
from typing import Optional

from .errors import StorageIsolationError


KERNEL_TABLES = frozenset(
    {
        "kernel_schema_meta",
        "kernel_clock",
        "kernel_executions",
        "kernel_events",
        "kernel_result_outbox",
        "kernel_effects",
        "kernel_effect_events",
    }
)

KERNEL_INDEXES = frozenset(
    {
        "kernel_executions_idempotency",
        "kernel_executions_claim",
        "kernel_events_identity",
        "kernel_events_execution_revision",
        "kernel_result_outbox_execution",
        "kernel_result_outbox_claim",
        "kernel_effect_events_identity",
    }
)


SCHEMA_SQL = """
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS kernel_schema_meta (
    component TEXT NOT NULL PRIMARY KEY CHECK (component = 'execution_kernel'),
    schema_version NOT NULL
        CHECK (typeof(schema_version) = 'integer' AND schema_version = 2)
);
INSERT OR IGNORE INTO kernel_schema_meta (component, schema_version)
    VALUES ('execution_kernel', 2);
CREATE TABLE IF NOT EXISTS kernel_clock (
    singleton INTEGER NOT NULL PRIMARY KEY CHECK (singleton = 1),
    watermark REAL NOT NULL CHECK (
        typeof(watermark) IN ('integer', 'real')
        AND watermark >= 0 AND watermark <= 1.7976931348623157e308
    ),
    event_sequence INTEGER NOT NULL CHECK (
        typeof(event_sequence) = 'integer' AND event_sequence >= 0
    )
);
INSERT OR IGNORE INTO kernel_clock (singleton, watermark, event_sequence)
    VALUES (1, 0, 0);
CREATE TABLE IF NOT EXISTS kernel_executions (
    execution_id TEXT NOT NULL PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    registry_revision TEXT NOT NULL,
    command_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'queued', 'leased', 'running', 'recovery_required',
        'succeeded', 'failed', 'timed_out', 'cancelled', 'dead'
    )),
    attempt INTEGER NOT NULL CHECK (typeof(attempt) = 'integer' AND attempt >= 0),
    redelivery_count INTEGER NOT NULL CHECK (
        typeof(redelivery_count) = 'integer' AND redelivery_count >= 0
    ),
    next_attempt_at REAL NOT NULL CHECK (
        typeof(next_attempt_at) IN ('integer', 'real')
        AND next_attempt_at >= 0 AND next_attempt_at <= 1.7976931348623157e308
    ),
    lease_id TEXT,
    lease_owner TEXT,
    fence INTEGER NOT NULL CHECK (typeof(fence) = 'integer' AND fence >= 0),
    lease_expires_at REAL,
    started_at REAL,
    result_json TEXT,
    recovery_effect_id TEXT,
    recovery_target_state TEXT CHECK (
        recovery_target_state IS NULL
        OR recovery_target_state IN ('queued', 'cancelled')
    ),
    recovery_reason TEXT,
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 1),
    created_at REAL NOT NULL CHECK (
        typeof(created_at) IN ('integer', 'real')
        AND created_at >= 0 AND created_at <= 1.7976931348623157e308
    ),
    updated_at REAL NOT NULL CHECK (
        typeof(updated_at) IN ('integer', 'real')
        AND updated_at >= created_at AND updated_at <= 1.7976931348623157e308
    ),
    CHECK (length(trim(execution_id)) > 0),
    CHECK (length(trim(idempotency_key)) > 0),
    CHECK (length(trim(registry_revision)) > 0),
    CHECK ((attempt = 0 AND fence = 0) OR (attempt >= 1 AND fence >= 1)),
    CHECK (
        (state IN ('leased', 'running') AND lease_id IS NOT NULL
            AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (state NOT IN ('leased', 'running') AND lease_id IS NULL
            AND lease_owner IS NULL AND lease_expires_at IS NULL)
    ),
    CHECK (
        (state IN ('succeeded', 'failed', 'timed_out', 'cancelled', 'dead'))
        = (result_json IS NOT NULL)
    ),
    CHECK (
        (state = 'recovery_required')
        = (recovery_effect_id IS NOT NULL AND recovery_target_state IS NOT NULL)
    ),
    CHECK (
        (state = 'recovery_required' AND recovery_target_state = 'queued'
            AND recovery_reason IS NULL)
        OR
        (state = 'recovery_required' AND recovery_target_state = 'cancelled'
            AND recovery_reason IS NOT NULL AND length(trim(recovery_reason)) > 0)
        OR
        (state != 'recovery_required' AND recovery_target_state IS NULL
            AND recovery_reason IS NULL)
    ),
    CHECK (
        (state IN ('running', 'recovery_required', 'succeeded', 'failed',
            'timed_out', 'cancelled', 'dead') AND started_at IS NOT NULL)
        OR (state IN ('queued', 'leased') AND started_at IS NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS kernel_executions_idempotency
    ON kernel_executions(idempotency_key);
CREATE INDEX IF NOT EXISTS kernel_executions_claim
    ON kernel_executions(state, registry_revision, next_attempt_at, created_at);
CREATE TABLE IF NOT EXISTS kernel_events (
    sequence INTEGER NOT NULL PRIMARY KEY CHECK (
        typeof(sequence) = 'integer' AND sequence >= 1
    ),
    event_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 1),
    event_type TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at REAL NOT NULL CHECK (
        typeof(created_at) IN ('integer', 'real')
        AND created_at >= 0 AND created_at <= 1.7976931348623157e308
    ),
    CHECK (length(trim(event_id)) > 0),
    CHECK (length(trim(execution_id)) > 0),
    CHECK (length(trim(event_type)) > 0),
    CHECK (length(trim(to_state)) > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS kernel_events_identity
    ON kernel_events(event_id);
CREATE UNIQUE INDEX IF NOT EXISTS kernel_events_execution_revision
    ON kernel_events(execution_id, revision);
CREATE TABLE IF NOT EXISTS kernel_result_outbox (
    result_id TEXT NOT NULL PRIMARY KEY,
    execution_id TEXT NOT NULL,
    result_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'delivering', 'delivered', 'dead')),
    lease_id TEXT,
    lease_owner TEXT,
    fence INTEGER NOT NULL CHECK (typeof(fence) = 'integer' AND fence >= 0),
    attempts INTEGER NOT NULL CHECK (typeof(attempts) = 'integer' AND attempts >= 0),
    max_attempts INTEGER NOT NULL CHECK (
        typeof(max_attempts) = 'integer' AND max_attempts >= 1
    ),
    lease_expires_at REAL,
    next_attempt_at REAL NOT NULL CHECK (
        typeof(next_attempt_at) IN ('integer', 'real')
        AND next_attempt_at >= 0 AND next_attempt_at <= 1.7976931348623157e308
    ),
    last_error_json TEXT,
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 1),
    created_at REAL NOT NULL CHECK (
        typeof(created_at) IN ('integer', 'real')
        AND created_at >= 0 AND created_at <= 1.7976931348623157e308
    ),
    updated_at REAL NOT NULL CHECK (
        typeof(updated_at) IN ('integer', 'real')
        AND updated_at >= created_at AND updated_at <= 1.7976931348623157e308
    ),
    CHECK (attempts <= max_attempts),
    CHECK (
        state != 'delivering'
        OR (lease_id IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS kernel_result_outbox_execution
    ON kernel_result_outbox(execution_id);
CREATE INDEX IF NOT EXISTS kernel_result_outbox_claim
    ON kernel_result_outbox(state, next_attempt_at, created_at);
CREATE TABLE IF NOT EXISTS kernel_effects (
    effect_id TEXT NOT NULL PRIMARY KEY,
    execution_id TEXT NOT NULL,
    name TEXT NOT NULL,
    request_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'prepared', 'performing', 'committed', 'indeterminate', 'not_applied'
    )),
    response_json TEXT,
    lease_id TEXT NOT NULL,
    claim_id TEXT,
    attempt INTEGER NOT NULL CHECK (typeof(attempt) = 'integer' AND attempt >= 1),
    fence INTEGER NOT NULL CHECK (typeof(fence) = 'integer' AND fence >= 1),
    prepared_at REAL NOT NULL CHECK (
        typeof(prepared_at) IN ('integer', 'real')
        AND prepared_at >= 0 AND prepared_at <= 1.7976931348623157e308
    ),
    committed_at REAL,
    indeterminate_at REAL,
    recovery_id TEXT,
    recovery_decision TEXT CHECK (
        recovery_decision IS NULL OR recovery_decision IN ('applied', 'not_applied')
    ),
    resolved_at REAL,
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 1),
    CHECK (length(trim(effect_id)) > 0),
    CHECK (length(trim(execution_id)) > 0),
    CHECK (length(trim(name)) > 0),
    CHECK (state != 'performing' OR claim_id IS NOT NULL),
    CHECK (state NOT IN ('prepared', 'not_applied') OR claim_id IS NULL),
    CHECK (state NOT IN ('prepared', 'performing') OR response_json IS NULL),
    CHECK (state != 'indeterminate' OR indeterminate_at IS NOT NULL),
    CHECK (state != 'committed' OR committed_at IS NOT NULL),
    CHECK (
        (recovery_id IS NULL AND recovery_decision IS NULL AND resolved_at IS NULL)
        OR (recovery_id IS NOT NULL AND recovery_decision IS NOT NULL AND resolved_at IS NOT NULL)
    )
);
CREATE TABLE IF NOT EXISTS kernel_effect_events (
    event_id TEXT NOT NULL PRIMARY KEY,
    effect_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 1),
    event_type TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at REAL NOT NULL CHECK (
        typeof(created_at) IN ('integer', 'real')
        AND created_at >= 0 AND created_at <= 1.7976931348623157e308
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS kernel_effect_events_identity
    ON kernel_effect_events(effect_id, revision);
COMMIT;
"""


EXPECTED_COLUMNS = {
    "kernel_schema_meta": (
        ("component", "TEXT", 1, 1), ("schema_version", "", 1, 0),
    ),
    "kernel_clock": (
        ("singleton", "INTEGER", 1, 1), ("watermark", "REAL", 1, 0),
        ("event_sequence", "INTEGER", 1, 0),
    ),
    "kernel_executions": (
        ("execution_id", "TEXT", 1, 1), ("idempotency_key", "TEXT", 1, 0),
        ("registry_revision", "TEXT", 1, 0), ("command_json", "TEXT", 1, 0),
        ("state", "TEXT", 1, 0), ("attempt", "INTEGER", 1, 0),
        ("redelivery_count", "INTEGER", 1, 0), ("next_attempt_at", "REAL", 1, 0),
        ("lease_id", "TEXT", 0, 0), ("lease_owner", "TEXT", 0, 0),
        ("fence", "INTEGER", 1, 0), ("lease_expires_at", "REAL", 0, 0),
        ("started_at", "REAL", 0, 0), ("result_json", "TEXT", 0, 0),
        ("recovery_effect_id", "TEXT", 0, 0),
        ("recovery_target_state", "TEXT", 0, 0),
        ("recovery_reason", "TEXT", 0, 0), ("revision", "INTEGER", 1, 0),
        ("created_at", "REAL", 1, 0), ("updated_at", "REAL", 1, 0),
    ),
    "kernel_events": (
        ("sequence", "INTEGER", 1, 1), ("event_id", "TEXT", 1, 0),
        ("execution_id", "TEXT", 1, 0), ("revision", "INTEGER", 1, 0),
        ("event_type", "TEXT", 1, 0), ("from_state", "TEXT", 0, 0),
        ("to_state", "TEXT", 1, 0), ("data_json", "TEXT", 1, 0),
        ("created_at", "REAL", 1, 0),
    ),
    "kernel_result_outbox": (
        ("result_id", "TEXT", 1, 1), ("execution_id", "TEXT", 1, 0),
        ("result_json", "TEXT", 1, 0), ("state", "TEXT", 1, 0),
        ("lease_id", "TEXT", 0, 0), ("lease_owner", "TEXT", 0, 0),
        ("fence", "INTEGER", 1, 0), ("attempts", "INTEGER", 1, 0),
        ("max_attempts", "INTEGER", 1, 0), ("lease_expires_at", "REAL", 0, 0),
        ("next_attempt_at", "REAL", 1, 0), ("last_error_json", "TEXT", 0, 0),
        ("revision", "INTEGER", 1, 0), ("created_at", "REAL", 1, 0),
        ("updated_at", "REAL", 1, 0),
    ),
    "kernel_effects": (
        ("effect_id", "TEXT", 1, 1), ("execution_id", "TEXT", 1, 0),
        ("name", "TEXT", 1, 0), ("request_json", "TEXT", 1, 0),
        ("state", "TEXT", 1, 0), ("response_json", "TEXT", 0, 0),
        ("lease_id", "TEXT", 1, 0), ("claim_id", "TEXT", 0, 0),
        ("attempt", "INTEGER", 1, 0), ("fence", "INTEGER", 1, 0),
        ("prepared_at", "REAL", 1, 0), ("committed_at", "REAL", 0, 0),
        ("indeterminate_at", "REAL", 0, 0), ("recovery_id", "TEXT", 0, 0),
        ("recovery_decision", "TEXT", 0, 0), ("resolved_at", "REAL", 0, 0),
        ("revision", "INTEGER", 1, 0),
    ),
    "kernel_effect_events": (
        ("event_id", "TEXT", 1, 1), ("effect_id", "TEXT", 1, 0),
        ("execution_id", "TEXT", 1, 0), ("revision", "INTEGER", 1, 0),
        ("event_type", "TEXT", 1, 0), ("from_state", "TEXT", 0, 0),
        ("to_state", "TEXT", 1, 0), ("data_json", "TEXT", 1, 0),
        ("created_at", "REAL", 1, 0),
    ),
}


SQL_REQUIREMENTS = {
    "kernel_schema_meta": (
        "check(component='execution_kernel')",
        "typeof(schema_version)='integer'andschema_version=2",
    ),
    "kernel_clock": (
        "check(singleton=1)",
        "typeof(watermark)in('integer','real')",
        "watermark>=0",
        "typeof(event_sequence)='integer'andevent_sequence>=0",
    ),
    "kernel_executions": (
        "check(statein(",
        "typeof(attempt)='integer'andattempt>=0",
        "typeof(redelivery_count)='integer'andredelivery_count>=0",
        "typeof(fence)='integer'andfence>=0",
        "typeof(revision)='integer'andrevision>=1",
        "length(trim(execution_id))>0",
        "length(trim(idempotency_key))>0",
        "length(trim(registry_revision))>0",
        "(attempt=0andfence=0)or(attempt>=1andfence>=1)",
        "statein('leased','running')andlease_idisnotnull",
        "state not in ('leased','running') and lease_id is null",
        "result_jsonisnotnull",
        "(state='recovery_required')=(recovery_effect_idisnotnullandrecovery_target_stateisnotnull)",
        "recovery_target_statein('queued','cancelled')",
        "recovery_target_state='queued'andrecovery_reasonisnull",
        "recovery_target_state='cancelled'andrecovery_reasonisnotnull",
        "started_atisnotnull",
    ),
    "kernel_events": (
        "check(typeof(sequence)='integer'andsequence>=1)",
        "typeof(revision)='integer'andrevision>=1",
        "length(trim(event_id))>0",
        "length(trim(execution_id))>0",
    ),
    "kernel_result_outbox": (
        "check(statein('pending','delivering','delivered','dead'))",
        "typeof(attempts)='integer'andattempts>=0",
        "typeof(max_attempts)='integer'andmax_attempts>=1",
        "attempts<=max_attempts",
        "state!='delivering'or(lease_idisnotnullandlease_ownerisnotnullandlease_expires_atisnotnull)",
    ),
    "kernel_effects": (
        "check(statein(",
        "'performing'",
        "typeof(attempt)='integer'andattempt>=1",
        "typeof(fence)='integer'andfence>=1",
        "typeof(revision)='integer'andrevision>=1",
        "length(trim(effect_id))>0",
        "length(trim(execution_id))>0",
        "length(trim(name))>0",
        "state!='performing'orclaim_idisnotnull",
        "state not in ('prepared','not_applied') or claim_id is null",
        "state not in ('prepared','performing') or response_json is null",
        "state!='indeterminate'orindeterminate_atisnotnull",
        "state!='committed'orcommitted_atisnotnull",
        "recovery_decisionin('applied','not_applied')",
    ),
    "kernel_effect_events": (
        "typeof(revision)='integer'andrevision>=1",
    ),
}


EXPECTED_INDEX_SQL = {
    "kernel_executions_idempotency": "createuniqueindexkernel_executions_idempotencyonkernel_executions(idempotency_key)",
    "kernel_executions_claim": "createindexkernel_executions_claimonkernel_executions(state,registry_revision,next_attempt_at,created_at)",
    "kernel_events_identity": "createuniqueindexkernel_events_identityonkernel_events(event_id)",
    "kernel_events_execution_revision": "createuniqueindexkernel_events_execution_revisiononkernel_events(execution_id,revision)",
    "kernel_result_outbox_execution": "createuniqueindexkernel_result_outbox_executiononkernel_result_outbox(execution_id)",
    "kernel_result_outbox_claim": "createindexkernel_result_outbox_claimonkernel_result_outbox(state,next_attempt_at,created_at)",
    "kernel_effect_events_identity": "createuniqueindexkernel_effect_events_identityonkernel_effect_events(effect_id,revision)",
}


def _normalize_sql(value: str) -> str:
    # Normalize syntax only. Quoted values (including spaces and letter case)
    # participate in CHECK semantics and must survive schema comparison.
    parts = re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\])", value)
    return "".join(part if index % 2 else re.sub(r"\s+", "", part.lower()).replace("ifnotexists", "")
                   for index, part in enumerate(parts))


def _expected_object_sql() -> dict[str, str]:
    """Extract canonical DDL from the bootstrap script without SQL parsing."""

    expected: dict[str, str] = {}
    names = KERNEL_TABLES | KERNEL_INDEXES
    for statement in SCHEMA_SQL.split(";"):
        normalized = _normalize_sql(statement)
        for name in names:
            if (
                f"createtable{name}(" in normalized
                or f"createindex{name}on" in normalized
                or f"createuniqueindex{name}on" in normalized
            ):
                expected[name] = normalized
                break
    if set(expected) != names:
        raise RuntimeError("internal execution-kernel schema manifest is incomplete")
    return expected


def existing_table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    # The host application owns other namespaces. Validate only Kernel objects;
    # the connection authorizer still denies reading/writing foreign tables.
    return {row[0] for row in rows}


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)


def _table_columns(connection: sqlite3.Connection, table: str) -> tuple[tuple, ...]:
    statements = {
        "kernel_schema_meta": "PRAGMA table_info(kernel_schema_meta)",
        "kernel_clock": "PRAGMA table_info(kernel_clock)",
        "kernel_executions": "PRAGMA table_info(kernel_executions)",
        "kernel_events": "PRAGMA table_info(kernel_events)",
        "kernel_result_outbox": "PRAGMA table_info(kernel_result_outbox)",
        "kernel_effects": "PRAGMA table_info(kernel_effects)",
        "kernel_effect_events": "PRAGMA table_info(kernel_effect_events)",
    }
    rows = connection.execute(statements[table]).fetchall()
    return tuple((row[1], row[2].upper(), row[3], row[5]) for row in rows)


def validate_schema(
    connection: sqlite3.Connection,
    kernel_names: set[str] | frozenset[str],
) -> None:
    if set(kernel_names) != set(KERNEL_TABLES):
        missing = sorted(KERNEL_TABLES - set(kernel_names))
        extra = sorted(set(kernel_names) - KERNEL_TABLES)
        raise StorageIsolationError(
            "incompatible execution-kernel table set; "
            f"missing={missing!r}, unexpected={extra!r}"
        )
    objects = connection.execute(
        """SELECT name, type, sql FROM sqlite_master
           WHERE name LIKE 'kernel_%' ORDER BY name"""
    ).fetchall()
    expected_objects = KERNEL_TABLES | KERNEL_INDEXES
    if {row["name"] for row in objects} != expected_objects:
        raise StorageIsolationError("incompatible execution-kernel schema object set")
    for table, expected in EXPECTED_COLUMNS.items():
        if _table_columns(connection, table) != expected:
            raise StorageIsolationError(f"incompatible v2 column schema: {table}")
    sql_by_name = {row["name"]: _normalize_sql(row["sql"] or "") for row in objects}
    expected_sql = _expected_object_sql()
    for name, expected in expected_sql.items():
        if sql_by_name.get(name) != expected:
            raise StorageIsolationError(f"incompatible exact schema definition: {name}")
    for table, fragments in SQL_REQUIREMENTS.items():
        if any(_normalize_sql(fragment) not in sql_by_name[table] for fragment in fragments):
            raise StorageIsolationError(f"weakened or incompatible CHECK schema: {table}")
    for name, expected in EXPECTED_INDEX_SQL.items():
        if sql_by_name.get(name) != expected:
            raise StorageIsolationError(f"incompatible index definition: {name}")
    meta = connection.execute(
        """SELECT component, schema_version, typeof(schema_version)
           FROM kernel_schema_meta"""
    ).fetchall()
    if (
        len(meta) != 1
        or meta[0]["component"] != "execution_kernel"
        or type(meta[0]["schema_version"]) is not int
        or meta[0]["schema_version"] != 2
        or meta[0][2] != "integer"
    ):
        raise StorageIsolationError(
            "kernel_schema_meta must contain exactly execution_kernel schema v2"
        )
    clock = connection.execute(
        """SELECT singleton, watermark, event_sequence,
                  typeof(watermark), typeof(event_sequence)
           FROM kernel_clock"""
    ).fetchall()
    if (
        len(clock) != 1
        or clock[0]["singleton"] != 1
        or type(clock[0]["event_sequence"]) is not int
        or clock[0]["event_sequence"] < 0
        or clock[0][3] not in {"integer", "real"}
        or clock[0][4] != "integer"
        or not math.isfinite(float(clock[0]["watermark"]))
        or clock[0]["watermark"] < 0
    ):
        raise StorageIsolationError("kernel_clock must contain one valid watermark row")
    events = connection.execute(
        "SELECT COALESCE(MAX(sequence), 0) AS maximum_sequence FROM kernel_events"
    ).fetchone()
    if (
        events is None
        or events["maximum_sequence"] != clock[0]["event_sequence"]
    ):
        raise StorageIsolationError("kernel global event sequence is inconsistent")


def install_authorizer(connection: sqlite3.Connection):
    read_tables = KERNEL_TABLES | {"sqlite_master", "sqlite_schema"}
    insert_tables = {
        "kernel_executions",
        "kernel_events",
        "kernel_result_outbox",
        "kernel_effects",
        "kernel_effect_events",
    }
    update_columns = {
        "kernel_clock": {"watermark", "event_sequence"},
        "kernel_executions": {
            "state", "attempt", "redelivery_count", "next_attempt_at", "lease_id",
            "lease_owner", "fence", "lease_expires_at", "started_at", "result_json",
            "recovery_effect_id", "recovery_target_state", "recovery_reason",
            "revision", "updated_at",
        },
        "kernel_result_outbox": {
            "state", "lease_id", "lease_owner", "fence", "attempts",
            "lease_expires_at", "next_attempt_at", "last_error_json", "revision",
            "updated_at",
        },
        "kernel_effects": {
            "state", "response_json", "lease_id", "claim_id", "attempt", "fence",
            "prepared_at", "committed_at", "indeterminate_at", "recovery_id",
            "recovery_decision", "resolved_at", "revision",
        },
    }
    denied = {
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_PRAGMA,
        sqlite3.SQLITE_ANALYZE,
        sqlite3.SQLITE_REINDEX,
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_CREATE_VTABLE,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_INDEX,
        sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER,
        sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_DROP_VTABLE,
    }

    def authorize(
        action: int,
        first: Optional[str],
        second: Optional[str],
        database: Optional[str],
        _source: Optional[str],
    ) -> int:
        if action in denied:
            return sqlite3.SQLITE_DENY
        if action in {
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_INSERT,
            sqlite3.SQLITE_UPDATE,
            sqlite3.SQLITE_DELETE,
        }:
            # Kernel schema has no views or triggers.  Refuse indirect access
            # so a pre-existing cross-layer trigger cannot borrow these
            # otherwise valid table/column permissions.
            if database != "main" or _source is not None:
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_READ:
                allowed = first in read_tables
            elif action == sqlite3.SQLITE_INSERT:
                allowed = first in insert_tables
            elif action == sqlite3.SQLITE_UPDATE:
                allowed = second in update_columns.get(first or "", set())
            else:
                allowed = False
            return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(authorize)
    return authorize
