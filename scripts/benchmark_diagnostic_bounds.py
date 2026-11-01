import json
import os
import resource
import sqlite3
import tempfile
import time
from pathlib import Path

from dispatcher_sdk.orchestrator.store import ORCHESTRATOR_SCHEMA_VERSION, SCHEMA, execute_schema, initialize_storage_tracking
from dispatcher_sdk.orchestrator.results import ResultsMixin
from dispatcher_sdk.orchestrator.notifications import NotificationsMixin
from dispatcher_sdk.orchestrator.run_diagnostics import inspect_run_diagnostics
from dispatcher_sdk.storage import inspect_storage

path = Path(tempfile.mkdtemp(prefix='sdk072-diagnostics-')) / 'probe.sqlite3'
db = sqlite3.connect(path)
execute_schema(db, SCHEMA)
results = ResultsMixin()
results.max_result_deliveries = 5
results._init_results(db)
NotificationsMixin._init_notifications(db)
db.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',?)", (ORCHESTRATOR_SCHEMA_VERSION,))
db.execute("INSERT INTO sdk_storage_identity VALUES(1,'probe','incarnation',1)")
db.execute('INSERT INTO sdk_storage_clock VALUES(1,0)')
initialize_storage_tracking(db)
db.execute("INSERT INTO sdk_runs VALUES('probe-run',7,'running')")
db.executemany('INSERT INTO sdk_run_items VALUES(?,?,?,?)',
    (('probe-run','task',f'task-{i:07d}','{}') for i in range(60000)))
db.executemany('INSERT INTO sdk_events(run_id,revision,kind,payload) VALUES(?,?,?,?)',
    (('probe-run',7,'probe','{}') for i in range(100000)))
db.commit()
db.close()

def measurement(label, call):
    started = time.monotonic()
    value = call()
    return {'case':label,'wall_seconds':time.monotonic()-started,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'result':value.to_dict() if hasattr(value, 'to_dict') else value}

out = {'database_bytes':os.path.getsize(path),'tasks':60000,'events':100000,'measurements':[]}
out['measurements'].append(measurement('schema', lambda: inspect_storage(path, check='schema', timeout_seconds=20)))
out['measurements'].append(measurement('bounded', lambda: inspect_run_diagnostics(path,'probe-run',task_limit=10,task_count_scan_limit=100,timeout_seconds=20)))
out['measurements'].append(measurement('budget_exhausted', lambda: inspect_run_diagnostics(path,'probe-run',timeout_seconds=0)))
out['measurements'].append(measurement('full', lambda: inspect_storage(path, check='full', timeout_seconds=20)))
bounded = out['measurements'][1]['result']
partial = out['measurements'][2]['result']
assert bounded['task_count'] is None and bounded['task_count_complete'] is False
assert bounded['task_count_lower_bound'] == 100 and len(bounded['tasks']) == 10
assert bounded['next_task_id'] is not None and bounded['complete'] is False
assert partial['complete'] is False and partial['task_count'] is None
assert out['measurements'][3]['result']['checks']['integrity'] == 'ok'
print(json.dumps(out, ensure_ascii=False))
