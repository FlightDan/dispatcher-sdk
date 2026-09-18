from pathlib import Path
import tempfile

from dispatcher_sdk import Dispatcher


def double(payload, context):
    return payload * 2


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "tasks.sqlite3"
        with Dispatcher(path, {"double": double}) as app:
            task = app.submit("double", 21, request_id="message-42")
            result = task.wait(timeout=10)
            print(result["value"])


if __name__ == "__main__":
    main()
