"""Exact SQLite schema validation and post-bootstrap authorization."""

from __future__ import annotations

import re
import math
import sqlite3
from typing import Optional

from .errors import StorageIsolationError


KERNEL_STORAGE_SCHEMA_VERSION = 4


KERNEL_TABLES = frozenset(
    {
        "kernel_schema_meta",
        "kernel_clock",
        "kernel_run_controls",
        "kernel_managed_executions",
        "kernel_executions",
        "kernel_events",
        "kernel_result_outbox",
        "kernel_effects",
        "kernel_effect_events",
        "kernel_execution_limits",
        "kernel_supervision",
        "kernel_progress_keys",
    }
)

KERNEL_INDEXES = frozenset(
    {
        "kernel_executions_idempotency",
        "kernel_executions_claim",
        "kernel_managed_executions_run",
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
        CHECK (typeof(schema_version) = 'integer' AND schema_version = 3)
);
INSERT OR IGNORE INTO kernel_schema_meta (component, schema_version)
    VALUES ('execution_kernel', 3);
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
CREATE TABLE IF NOT EXISTS kernel_run_controls (
    run_id TEXT NOT NULL PRIMARY KEY CHECK (length(trim(run_id)) > 0),
    control_epoch INTEGER NOT NULL CHECK (
        typeof(control_epoch) = 'integer' AND control_epoch >= 0
    ),
    generation INTEGER NOT NULL CHECK (
        typeof(generation) = 'integer' AND generation >= 0
    ),
    state TEXT NOT NULL CHECK (state IN ('active', 'pausing', 'paused')),
    max_claims INTEGER NOT NULL CHECK (
        typeof(max_claims) = 'integer' AND max_claims >= 0
    ),
    claims_used INTEGER NOT NULL CHECK (
        typeof(claims_used) = 'integer' AND claims_used >= 0 AND claims_used <= max_claims
    ),
    deadline_at REAL NOT NULL CHECK (
        typeof(deadline_at) IN ('integer', 'real')
        AND deadline_at >= 0 AND deadline_at <= 1.7976931348623157e308
    )
);
CREATE TABLE IF NOT EXISTS kernel_managed_executions (
    execution_id TEXT NOT NULL PRIMARY KEY CHECK (
        length(trim(execution_id)) > 0 AND substr(execution_id, 1, 12) = 'sdk-managed:'
    ),
    run_id TEXT NOT NULL CHECK (length(trim(run_id)) > 0),
    generation INTEGER NOT NULL CHECK (
        typeof(generation) = 'integer' AND generation >= 0
    ),
    drain_allowed INTEGER NOT NULL CHECK (
        typeof(drain_allowed) = 'integer' AND drain_allowed IN (0, 1)
    ),
    FOREIGN KEY (run_id) REFERENCES kernel_run_controls(run_id)
);
CREATE INDEX IF NOT EXISTS kernel_managed_executions_run
    ON kernel_managed_executions(run_id, generation, drain_allowed, execution_id);
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

# The former layout stays available only to explicit copy upgrades. New writers
# reject that marker rather than installing control tables on an ordinary open.
KERNEL_SCHEMA_V3 = SCHEMA_SQL
SUPERVISION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kernel_execution_limits (
    execution_id TEXT NOT NULL PRIMARY KEY,
    envelope_json TEXT NOT NULL,
    parent_execution_id TEXT,
    parent_attempt INTEGER,
    parent_fence INTEGER,
    depth INTEGER NOT NULL DEFAULT 0 CHECK (depth >= 0),
    entry_state TEXT NOT NULL DEFAULT 'unentered' CHECK (entry_state IN ('unentered','pending','confirmed')),
    entry_attempt INTEGER,
    entry_fence INTEGER,
    CHECK ((entry_state='unentered' AND entry_attempt IS NULL AND entry_fence IS NULL)
        OR (entry_state IN ('pending','confirmed') AND entry_attempt >= 1 AND entry_fence >= 1)),
    FOREIGN KEY (execution_id) REFERENCES kernel_executions(execution_id)
);
CREATE TABLE IF NOT EXISTS kernel_supervision (
    execution_id TEXT NOT NULL PRIMARY KEY,
    attempt INTEGER NOT NULL CHECK (attempt >= 0),
    fence INTEGER NOT NULL CHECK (fence >= 0),
    progress_revision INTEGER NOT NULL DEFAULT 0 CHECK (progress_revision >= 0),
    progress_at REAL,
    episode_id TEXT,
    policy_version TEXT,
    episode_progress_revision INTEGER,
    FOREIGN KEY (execution_id) REFERENCES kernel_executions(execution_id)
);
CREATE TABLE IF NOT EXISTS kernel_progress_keys (
    execution_id TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK (attempt >= 1),
    event_id TEXT NOT NULL CHECK (length(event_id) > 0),
    progress_revision INTEGER NOT NULL CHECK (progress_revision >= 1),
    PRIMARY KEY (execution_id, attempt, event_id),
    FOREIGN KEY (execution_id) REFERENCES kernel_executions(execution_id)
);
"""
SCHEMA_SQL = (KERNEL_SCHEMA_V3
              .replace("schema_version = 3", "schema_version = 4", 1)
              .replace("VALUES ('execution_kernel', 3)", "VALUES ('execution_kernel', 4)", 1)
              .replace("COMMIT;", SUPERVISION_SCHEMA_SQL + "COMMIT;", 1))


def _schema_v2_from_v3() -> str:
    """Build the exact supported v2 layout from the unchanged v2 objects.

    Kernel v3 only adds two tables and their index, and changes the schema
    marker constraint/value. Keeping the old DDL derivation here makes the
    explicit copy-upgrade validator compare against the former exact layout
    without duplicating the much larger execution/effect schema text.
    """

    removed_prefixes = (
        "CREATE TABLE IF NOT EXISTS kernel_run_controls",
        "CREATE TABLE IF NOT EXISTS kernel_managed_executions",
        "CREATE INDEX IF NOT EXISTS kernel_managed_executions_run",
    )
    statements: list[str] = []
    for raw in KERNEL_SCHEMA_V3.split(";"):
        statement = raw.strip()
        if not statement:
            continue
        if statement.startswith(removed_prefixes):
            continue
        if statement.startswith("CREATE TABLE IF NOT EXISTS kernel_schema_meta"):
            statement = statement.replace("schema_version = 3", "schema_version = 2", 1)
        elif statement.startswith("INSERT OR IGNORE INTO kernel_schema_meta"):
            statement = statement.replace(
                "VALUES ('execution_kernel', 3)",
                "VALUES ('execution_kernel', 2)",
                1,
            )
        statements.append(statement)
    if not any("schema_version = 2" in statement for statement in statements):
        raise RuntimeError("internal Kernel v2 schema derivation failed")
    return ";\n".join(statements) + ";"


# Used only by explicit copy migration. Opening a v2 Kernel store in a v3
# writer remains a hard error; this reference never runs during normal open.
KERNEL_SCHEMA_V2 = _schema_v2_from_v3()


EXPECTED_COLUMNS = {
    "kernel_execution_limits": (
        ("execution_id", "TEXT", 1, 1), ("envelope_json", "TEXT", 1, 0),
        ("parent_execution_id", "TEXT", 0, 0), ("parent_attempt", "INTEGER", 0, 0),
        ("parent_fence", "INTEGER", 0, 0), ("depth", "INTEGER", 1, 0),
        ("entry_state", "TEXT", 1, 0), ("entry_attempt", "INTEGER", 0, 0),
        ("entry_fence", "INTEGER", 0, 0),
    ),
    "kernel_supervision": (
        ("execution_id", "TEXT", 1, 1), ("attempt", "INTEGER", 1, 0),
        ("fence", "INTEGER", 1, 0), ("progress_revision", "INTEGER", 1, 0),
        ("progress_at", "REAL", 0, 0), ("episode_id", "TEXT", 0, 0),
        ("policy_version", "TEXT", 0, 0), ("episode_progress_revision", "INTEGER", 0, 0),
    ),
    "kernel_progress_keys": (
        ("execution_id", "TEXT", 1, 1), ("attempt", "INTEGER", 1, 2),
        ("event_id", "TEXT", 1, 3), ("progress_revision", "INTEGER", 1, 0),
    ),
    "kernel_schema_meta": (
        ("component", "TEXT", 1, 1), ("schema_version", "", 1, 0),
    ),
    "kernel_clock": (
        ("singleton", "INTEGER", 1, 1), ("watermark", "REAL", 1, 0),
        ("event_sequence", "INTEGER", 1, 0),
    ),
    "kernel_run_controls": (
        ("run_id", "TEXT", 1, 1), ("control_epoch", "INTEGER", 1, 0),
        ("generation", "INTEGER", 1, 0), ("state", "TEXT", 1, 0),
        ("max_claims", "INTEGER", 1, 0), ("claims_used", "INTEGER", 1, 0),
        ("deadline_at", "REAL", 1, 0),
    ),
    "kernel_managed_executions": (
        ("execution_id", "TEXT", 1, 1), ("run_id", "TEXT", 1, 0),
        ("generation", "INTEGER", 1, 0), ("drain_allowed", "INTEGER", 1, 0),
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
        "typeof(schema_version)='integer'andschema_version=4",
    ),
    "kernel_clock": (
        "check(singleton=1)",
        "typeof(watermark)in('integer','real')",
        "watermark>=0",
        "typeof(event_sequence)='integer'andevent_sequence>=0",
    ),
    "kernel_run_controls": (
        "length(trim(run_id))>0",
        "typeof(control_epoch)='integer'andcontrol_epoch>=0",
        "typeof(generation)='integer'andgeneration>=0",
        "statein('active','pausing','paused')",
        "typeof(max_claims)='integer'andmax_claims>=0",
        "typeof(claims_used)='integer'andclaims_used>=0andclaims_used<=max_claims",
        "typeof(deadline_at)in('integer','real')",
        "deadline_at>=0",
        "deadline_at<=1.7976931348623157e308",
    ),
    "kernel_managed_executions": (
        "length(trim(execution_id))>0",
        "substr(execution_id,1,12)='sdk-managed:'",
        "length(trim(run_id))>0",
        "typeof(generation)='integer'andgeneration>=0",
        "typeof(drain_allowed)='integer'anddrain_allowedin(0,1)",
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
    "kernel_managed_executions_run": "createindexkernel_managed_executions_runonkernel_managed_executions(run_id,generation,drain_allowed,execution_id)",
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


def _schema_statement_for(name: str, schema_sql: str = SCHEMA_SQL) -> str:
    for raw in schema_sql.split(";"):
        statement = raw.strip()
        normalized = _normalize_sql(statement)
        if (
            f"createtable{name.lower()}(" in normalized
            or f"createindex{name.lower()}on" in normalized
            or f"createuniqueindex{name.lower()}on" in normalized
        ):
            return statement
    raise RuntimeError(f"internal Kernel schema statement is missing: {name}")


def validate_kernel_schema_v2(connection: sqlite3.Connection) -> None:
    """Require the exact Kernel v2 schema before an explicit copy upgrade."""

    v2_tables = KERNEL_TABLES - {
        "kernel_run_controls",
        "kernel_managed_executions",
        "kernel_execution_limits",
        "kernel_supervision",
        "kernel_progress_keys",
    }
    actual_tables = {
        name
        for name in existing_table_names(connection)
        if name.startswith("kernel_")
    }
    if actual_tables != set(v2_tables):
        raise StorageIsolationError(
            "incompatible Kernel v2 table set; "
            f"missing={sorted(v2_tables - actual_tables)!r}, "
            f"unexpected={sorted(actual_tables - v2_tables)!r}"
        )

    reference = sqlite3.connect(":memory:")
    try:
        reference.executescript(KERNEL_SCHEMA_V2)
        expected_objects = {
            row[0]: (row[1], _normalize_sql(row[2] or ""))
            for row in reference.execute(
                "SELECT name,type,sql FROM sqlite_master WHERE name LIKE 'kernel_%'"
            ).fetchall()
        }
        actual_objects = {
            row[0]: (row[1], _normalize_sql(row[2] or ""))
            for row in connection.execute(
                "SELECT name,type,sql FROM sqlite_master WHERE name LIKE 'kernel_%'"
            ).fetchall()
        }
        if actual_objects != expected_objects:
            raise StorageIsolationError("Kernel v2 schema differs from the supported exact layout")
        for table in v2_tables:
            if _table_columns(connection, table) != _table_columns(reference, table):
                raise StorageIsolationError(f"incompatible Kernel v2 column schema: {table}")
    finally:
        reference.close()

    marker = connection.execute(
        "SELECT component,schema_version,typeof(schema_version) FROM kernel_schema_meta"
    ).fetchall()
    if (
        len(marker) != 1
        or marker[0][0] != "execution_kernel"
        or type(marker[0][1]) is not int
        or marker[0][1] != 2
        or marker[0][2] != "integer"
    ):
        raise StorageIsolationError("kernel_schema_meta must contain exactly execution_kernel schema v2")
    clock = connection.execute(
        "SELECT singleton,watermark,event_sequence,typeof(watermark),typeof(event_sequence) "
        "FROM kernel_clock"
    ).fetchall()
    if (
        len(clock) != 1
        or clock[0][0] != 1
        or type(clock[0][2]) is not int
        or clock[0][2] < 0
        or clock[0][3] not in {"integer", "real"}
        or clock[0][4] != "integer"
        or not math.isfinite(float(clock[0][1]))
        or clock[0][1] < 0
    ):
        raise StorageIsolationError("Kernel v2 clock row is invalid")
    events = connection.execute(
        "SELECT COALESCE(MAX(sequence),0) FROM kernel_events"
    ).fetchone()
    if events is None or events[0] != clock[0][2]:
        raise StorageIsolationError("Kernel v2 global event sequence is inconsistent")


def upgrade_kernel_schema_v2_to_v3(connection: sqlite3.Connection) -> None:
    """Upgrade an exact Kernel v2 schema in a private copy, preserving rows.

    This is deliberately explicit and never called by SQLiteKernel open. The
    caller must pass an idle writable connection to a copied database. New
    managed control tables start empty; existing execution data is unchanged.
    """

    if not isinstance(connection, sqlite3.Connection):
        raise TypeError("connection must be a sqlite3.Connection")
    if connection.in_transaction:
        raise RuntimeError("Kernel schema upgrade requires an idle connection")
    previous_row_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            # Revalidate after taking the write lock so the checked layout is
            # the one being upgraded, even when called outside a maintenance copy.
            validate_kernel_schema_v2(connection)
            connection.execute("DROP TABLE kernel_schema_meta")
            connection.execute(_schema_statement_for("kernel_schema_meta", KERNEL_SCHEMA_V3))
            connection.execute(
                "INSERT INTO kernel_schema_meta(component,schema_version) VALUES(?,?)",
                ("execution_kernel", 3),
            )
            for name in (
                "kernel_run_controls",
                "kernel_managed_executions",
                "kernel_managed_executions_run",
            ):
                connection.execute(_schema_statement_for(name, KERNEL_SCHEMA_V3))
            validate_kernel_schema_v3(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        connection.row_factory = previous_row_factory


def validate_kernel_schema_v3(connection: sqlite3.Connection) -> None:
    """Validate the former exact layout without authorizing a writer."""
    reference = sqlite3.connect(":memory:")
    try:
        reference.executescript(KERNEL_SCHEMA_V3)
        query = "SELECT name,type,sql FROM sqlite_master WHERE name LIKE 'kernel_%'"
        expected = {row[0]: (row[1], _normalize_sql(row[2] or ""))
                    for row in reference.execute(query)}
        actual = {row[0]: (row[1], _normalize_sql(row[2] or ""))
                  for row in connection.execute(query)}
        if actual != expected:
            raise StorageIsolationError("Kernel v3 schema differs from its exact layout")
        marker = connection.execute(
            "SELECT component,schema_version,typeof(schema_version) FROM kernel_schema_meta"
        ).fetchall()
        if len(marker) != 1 or tuple(marker[0]) != ("execution_kernel", 3, "integer"):
            raise StorageIsolationError("invalid Kernel v3 schema marker")
        clock = connection.execute(
            "SELECT singleton,watermark,event_sequence FROM kernel_clock"
        ).fetchall()
        if (len(clock) != 1 or clock[0][0] != 1
                or type(clock[0][2]) is not int or clock[0][2] < 0
                or not math.isfinite(float(clock[0][1])) or clock[0][1] < 0):
            raise StorageIsolationError("invalid Kernel v3 clock")
        maximum = connection.execute(
            "SELECT COALESCE(MAX(sequence),0) FROM kernel_events"
        ).fetchone()[0]
        if maximum != clock[0][2]:
            raise StorageIsolationError("inconsistent Kernel v3 event sequence")
    finally:
        reference.close()


def upgrade_kernel_schema_v3_to_v4(connection: sqlite3.Connection) -> None:
    """Explicitly upgrade a private copy; historical execution rows stay intact."""
    if connection.in_transaction:
        raise RuntimeError("Kernel schema upgrade requires an idle connection")
    previous_row_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            validate_kernel_schema_v3(connection)
            connection.execute("DROP TABLE kernel_schema_meta")
            connection.execute(_schema_statement_for("kernel_schema_meta"))
            connection.execute(
                "INSERT INTO kernel_schema_meta(component,schema_version) VALUES(?,?)",
                ("execution_kernel", KERNEL_STORAGE_SCHEMA_VERSION),
            )
            for name in ("kernel_execution_limits", "kernel_supervision", "kernel_progress_keys"):
                connection.execute(_schema_statement_for(name))
            validate_schema(connection, KERNEL_TABLES)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        connection.row_factory = previous_row_factory


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
        "kernel_run_controls": "PRAGMA table_info(kernel_run_controls)",
        "kernel_managed_executions": "PRAGMA table_info(kernel_managed_executions)",
        "kernel_executions": "PRAGMA table_info(kernel_executions)",
        "kernel_events": "PRAGMA table_info(kernel_events)",
        "kernel_result_outbox": "PRAGMA table_info(kernel_result_outbox)",
        "kernel_effects": "PRAGMA table_info(kernel_effects)",
        "kernel_effect_events": "PRAGMA table_info(kernel_effect_events)",
        "kernel_execution_limits": "PRAGMA table_info(kernel_execution_limits)",
        "kernel_supervision": "PRAGMA table_info(kernel_supervision)",
        "kernel_progress_keys": "PRAGMA table_info(kernel_progress_keys)",
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
            raise StorageIsolationError(f"incompatible column schema: {table}")
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
        or meta[0]["schema_version"] != KERNEL_STORAGE_SCHEMA_VERSION
        or meta[0][2] != "integer"
    ):
        raise StorageIsolationError(
            f"kernel_schema_meta must contain exactly execution_kernel schema v{KERNEL_STORAGE_SCHEMA_VERSION}"
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
        "kernel_run_controls",
        "kernel_managed_executions",
        "kernel_executions",
        "kernel_events",
        "kernel_result_outbox",
        "kernel_effects",
        "kernel_effect_events",
        "kernel_execution_limits",
        "kernel_supervision",
        "kernel_progress_keys",
    }
    update_columns = {
        "kernel_execution_limits": {"envelope_json", "parent_execution_id", "parent_attempt", "parent_fence", "depth",
            "entry_state", "entry_attempt", "entry_fence"},
        "kernel_supervision": {
            "attempt", "fence", "progress_revision", "progress_at", "episode_id",
            "policy_version", "episode_progress_revision",
        },
        "kernel_clock": {"watermark", "event_sequence"},
        "kernel_run_controls": {
            "control_epoch", "generation", "state", "claims_used",
        },
        "kernel_managed_executions": {"drain_allowed"},
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
