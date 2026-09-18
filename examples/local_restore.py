"""Manual same-host recovery drill; run after installing the SDK."""
from pathlib import Path
import secrets
import tempfile

from dispatcher_sdk import Dispatcher
from dispatcher_sdk.storage_activation import activate_restored_snapshot
from dispatcher_sdk.storage_snapshots import (
    StoreGroupDescriptor, restore_snapshot, snapshot_store_group,
)


def double(payload, context):
    return payload * 2


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "source.sqlite3"
        handlers = {"double": double}
        # Construction can enqueue without executing work. Close all owners
        # before snapshotting; keep the source stopped throughout the handoff.
        app = Dispatcher(source, handlers)
        try:
            app.submit("double", 21, request_id="saved-input")
        finally:
            app.close()
        # Production keys belong in deployment secrets, outside the snapshot.
        key = secrets.token_bytes(32)
        snapshot_store_group(
            StoreGroupDescriptor({"application": source}), root / "backup",
            signing_key=key, owner_id="local-drill")
        restore_snapshot(root / "backup", root / "restored", key)
        activated = activate_restored_snapshot(
            root / "restored", root / "successor", signing_key=key,
            operation_id="local-drill-1", handlers=handlers, owner_id="local-drill")
        with Dispatcher(activated.components["application"], handlers) as recovered:
            print(recovered.task("saved-input").wait(timeout=10)["value"])
        print("Original source retired; restored task completed")


if __name__ == "__main__":
    main()
