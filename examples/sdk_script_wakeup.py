"""After installing the SDK: python examples/sdk_script_wakeup.py.

A durable application inbox demonstrates the callback boundary. Replace its
consumer with your application's Agent conversation launcher. Requires native Windows or POSIX process isolation.
"""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import threading

from dispatcher_sdk.execution_kernel import Kernel, ScriptSpec, script_handlers
from dispatcher_sdk.orchestrator import Orchestrator, OrchestratorHost


def main():
    with tempfile.TemporaryDirectory(prefix='sdk-wakeup-') as directory:
        root = Path(directory)
        inbox = root / 'application-inbox.sqlite3'
        with closing(sqlite3.connect(inbox)) as connection, connection:
            connection.execute('CREATE TABLE inbox (notification_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        accepted = threading.Event()

        def wake_agent(notification):
            with closing(sqlite3.connect(inbox)) as connection, connection:
                connection.execute('INSERT OR IGNORE INTO inbox VALUES(?,?)',
                                   (notification['notification_id'], json.dumps(notification)))
            accepted.set()

        runtime = Kernel.open_sqlite(root / 'work.sqlite3', script_handlers(), isolation_mode='process')
        orch = Orchestrator(root / 'work.sqlite3', runtime.kernel, runtime=runtime)
        orch.create_run('example', command_id='create')
        command = ScriptSpec("print('report ready')", (sys.executable, '-u'), root, root / 'logs').command(
            execution_id='script-1', idempotency_key='script-1', registry_revision=runtime.registry_revision,
            correlation_id='example', timeout_seconds=10)
        with OrchestratorHost(orch, wake_agent):
            orch.apply_operations('example', command_id='submit', expected_revision=0, operations=[
                {'kind': 'add_task', 'task_id': 'report', 'command': command.to_dict()},
                {'kind': 'watch_task', 'task_id': 'report', 'watch_id': 'report-wake',
                 'target': {'conversation_id': 'conversation-42'}},
                {'kind': 'dispatch', 'task_id': 'report'},
            ])
            # Demo process lifetime: wait on a Python event, with no LLM polling.
            if not accepted.wait(15):
                raise TimeoutError('demo did not receive its callback')
        with closing(sqlite3.connect(inbox)) as connection, connection:
            notification = json.loads(connection.execute('SELECT payload FROM inbox').fetchone()[0])
        assert notification['state'] == 'succeeded', notification
        assert notification['result']['value']['stdout']['tail'].strip() == 'report ready'
        orch.close()
        print(f"Wake {notification['target']['conversation_id']}: {notification['state']}")
        print(notification['result']['value']['stdout']['tail'].strip())


if __name__ == '__main__':
    main()
