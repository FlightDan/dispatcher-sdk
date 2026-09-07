"""Commit projection effects and event deduplication in one SQLite transaction."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile

from dispatcher_sdk.orchestrator import Orchestrator, ProjectionConsumer, ProjectionEventIdentity, RunEvent
from dispatcher_sdk.orchestrator import ProjectionDisposition


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with Orchestrator.open_sqlite(Path(directory) / "source.sqlite", {}, isolation_mode="thread") as sdk:
            sdk.create_run("demo", command_id="create")
            projection_path = Path(directory) / "projection.sqlite"
            with closing(sqlite3.connect(projection_path)) as connection:
                connection.executescript("""
                    CREATE TABLE receipts(source TEXT, run TEXT, sequence INTEGER,
                                          PRIMARY KEY(source,run,sequence));
                    CREATE TABLE totals(kind TEXT PRIMARY KEY, count INTEGER NOT NULL);
                """)

            def persist(identity: ProjectionEventIdentity, event: RunEvent) -> ProjectionDisposition:
                with closing(sqlite3.connect(projection_path)) as connection:
                    with connection:
                        inserted = connection.execute(
                            "INSERT OR IGNORE INTO receipts VALUES(?,?,?)",
                            (identity.source_id, identity.run_id, identity.sequence)).rowcount
                        if inserted:
                            connection.execute(
                                "INSERT INTO totals VALUES(?,1) ON CONFLICT(kind) "
                                "DO UPDATE SET count=count+1", (event["kind"],))
                    # Return only after the transaction commits.
                    return "persisted" if inserted else "already_present"

            # Preserve this namespace for this logical source across restarts.
            consumer = ProjectionConsumer(sdk, source_id="orders-production", subscription="totals-v1")
            report = consumer.drain("demo", persist)
            assert report.status == "completed", report
            # A different subscription explicitly replays historical events.
            replay = ProjectionConsumer(sdk, source_id="orders-production", subscription="audit-replay")
            replay_report = replay.drain("demo", persist)
            assert replay_report.replayed == report.processed
            print(report.to_dict())


if __name__ == "__main__":
    main()
