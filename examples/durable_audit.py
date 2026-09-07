"""Run with: PYTHONPATH=src python3 examples/durable_audit.py.

An application-owned SQLite audit sink, using only public SDK APIs.
The source_id must be stable and unique for the SDK database/event stream.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.orchestrator import Orchestrator, RevisionConflict


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


class AuditSink:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    source_id TEXT, run_id TEXT, sequence INTEGER, content TEXT NOT NULL,
                    PRIMARY KEY (source_id, run_id, sequence));
                CREATE TABLE IF NOT EXISTS pending_ack (
                    source_id TEXT, run_id TEXT, subscription TEXT, request TEXT NOT NULL,
                    PRIMARY KEY (source_id, run_id, subscription));
            """)

    def pending(self, source_id, run_id, subscription):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT request FROM pending_ack WHERE source_id=? AND run_id=? "
                             "AND subscription=?", (source_id, run_id, subscription)).fetchone()
            return json.loads(row[0]) if row else None

    def commit(self, source_id, run_id, events, request, *, fail=False):
        with closing(sqlite3.connect(self.path)) as db, db:
            for event in events:
                identity = (source_id, run_id, event["sequence"])
                content = canonical(event)
                previous = db.execute("SELECT content FROM audit_events WHERE source_id=? "
                                      "AND run_id=? AND sequence=?", identity).fetchone()
                if previous is None:
                    db.execute("INSERT INTO audit_events VALUES(?,?,?,?)", (*identity, content))
                elif previous[0] != content:
                    raise ValueError(f"conflicting content for audit event {identity}")
                # Same identity AND content is successful duplicate delivery.
            if fail:
                raise OSError("simulated audit write failure")
            db.execute("INSERT INTO pending_ack VALUES(?,?,?,?)",
                       (source_id, run_id, request["subscription"], canonical(request)))
        # Only here have both the audit events and exact ACK request committed.

    def clear_pending(self, source_id, run_id, subscription):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM pending_ack WHERE source_id=? AND run_id=? AND subscription=?",
                       (source_id, run_id, subscription))

    def count(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]


def drain(sdk, sink, source_id, run_id, *, subscription="audit", page_size=100,
          max_rounds=100, fail_sink=False, after_commit=None):
    """Drain a fixed observed watermark; one writer per source/run/subscription.

    Errors leave the cursor unchanged for the affected batch. A bounded retry
    budget prevents unending retries under concurrent Run changes. A later call
    can resume safely, including after a terminal Run or process restart.
    """
    watermark = sdk.observe(run_id, subscription=subscription, limit=page_size)["event_high_watermark"]
    for _ in range(max_rounds):
        request = sink.pending(source_id, run_id, subscription)
        if request is None:
            observed = sdk.observe(run_id, subscription=subscription, limit=page_size)
            if observed["cursor"] >= watermark:
                return watermark
            events = [event for event in observed["events"] if event["sequence"] <= watermark]
            if not events:
                raise RuntimeError("no events available before audit watermark")
            request = {"expected_revision": observed["snapshot"]["revision"],
                       "subscription": subscription, "expected_cursor": observed["cursor"],
                       "advance_to": events[-1]["sequence"]}
            identity = canonical([source_id, run_id, request]).encode()
            request["command_id"] = "audit-ack:" + hashlib.sha256(identity).hexdigest()
            sink.commit(source_id, run_id, events, request, fail=fail_sink)
            if after_commit is not None:
                after_commit()
        try:
            sdk.acknowledge_events(run_id, **request)
        except RevisionConflict:
            # No ACK committed. Keep durable events, re-observe and use new
            # command content/identity. Matching duplicate events are harmless.
            sink.clear_pending(source_id, run_id, subscription)
            continue
        # Unknown errors leave the full request for exact replay next time.
        sink.clear_pending(source_id, run_id, subscription)
        if request["advance_to"] >= watermark:
            return watermark
    raise TimeoutError("audit drain retry/page budget exhausted; call again to resume")


def main():
    with TemporaryDirectory(prefix="sdk-audit-") as directory:
        root = Path(directory)
        with Kernel.open_sqlite(root / "sdk.sqlite3", {}, isolation_mode="thread") as runtime:
            sdk = Orchestrator(root / "sdk.sqlite3", runtime.kernel, runtime=runtime)
            try:
                sink = AuditSink(root / "application-audit.sqlite3")
                source_id, run_id = "example-sdk-stream-v1", "example"
                sdk.create_run(run_id, command_id="create")
                for index in range(205):
                    sdk.apply_operations(run_id, command_id=f"signal-{index}", expected_revision=index,
                                         operations=[{"kind": "signal", "signal_id": str(index), "payload": index}])
                sdk.apply_operations(run_id, command_id="finish", expected_revision=205,
                                     operations=[{"kind": "finish", "state": "succeeded"}])
                assert sdk.get_run(run_id)["state"] == "succeeded"
                try:
                    drain(sdk, sink, source_id, run_id, fail_sink=True)
                except OSError:
                    pass
                else:
                    raise AssertionError("expected simulated sink failure")
                assert sdk.get_subscription(run_id, "audit") == 0 and sink.count() == 0

                def crash_after_commit():
                    raise RuntimeError("simulated crash after durable audit commit")

                try:
                    drain(sdk, sink, source_id, run_id, after_commit=crash_after_commit)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("expected simulated crash")
                assert sdk.get_subscription(run_id, "audit") == 0 and sink.count() == 100
                sink = AuditSink(root / "application-audit.sqlite3")
                watermark = drain(sdk, sink, source_id, run_id)
                assert sdk.get_subscription(run_id, "audit") == watermark
                assert sink.count() == 207
                # Replay is independent of the acknowledged subscription cursor.
                event = sdk.read_events(run_id, after=0, limit=1)[0]
                assert event["sequence"] <= watermark
                print(f"Audited {sink.count()} events from terminal Run; cursor={watermark}")
            finally:
                sdk.close()


if __name__ == "__main__":
    main()
