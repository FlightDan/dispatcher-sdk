import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.orchestrator.contracts import OrchestrationError, canonical
from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
from dispatcher_sdk.orchestrator.projection_storage import ProjectionStorage
from dispatcher_sdk.orchestrator.projection_stream import STREAM_POINTER_PREFIX
from dispatcher_sdk.orchestrator.streamed_install import install_streamed_projection


class StreamedInstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'run.db'
        self.storage = ProjectionStorage(Path(tmp.name) / 'bytes.db')
        identity = self.storage.identity()
        self.source = {'stream_id':'source','binding':{'kind':'source'},'total_bytes':7,**identity}
        self.target = {'stream_id':'target','binding':{'kind':'target'},'total_bytes':7,**identity}
        for pointer, data in ((self.source,b'{"a":1}'), (self.target,b'{"a":2}')):
            self.storage.create(pointer['stream_id'], total_bytes=7, binding=pointer['binding'])
            self.storage.append(pointer['stream_id'], sequence=0, data=data, complete=True)
        self.declaration = {'stream_version':1,'revision':{'v':2},'source_pointer':self.source,
                            'target_pointer':self.target,'content_pages':{'source_application_state':{},'target_application_state':{}}}
        self.expected = {'operation_id':'op','run_id':'run','kernel_store_id':'kernel','orchestrator_store_id':'orch','orchestrator_incarnation':'inc'}
        self.claim = {**self.expected,'source_revision':1,'source_epoch':2,'source_generation':3,
                      'declaration':self.declaration,'lease_id':'lease','lease_fence':1}
        envelope = {'decision_id':'op','operation_id':'op','barrier_operation_id':'op','run_id':'run',
                    'orchestrator_store_id':'orch','orchestrator_incarnation':'inc','kernel_store_id':'kernel',
                    'source_revision':1,'source_generation':3,'source_control_epoch':2,'target_generation':4,
                    'deployment':{},'revision':{'v':2},'source_application_state':None,
                    'target_application_state':None,'content_pages':self.declaration['content_pages'],
                    'migration_version':'m','application_projection_version':'p'}
        receipt = {'kind':'paused_revision_install','decision':envelope,'activation':'closed','target_control_epoch':3,
                   'claims_used':1,'max_claims':5,'deadline_at':100,'worker_principal':'worker','worker_expires_at':90}
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE sdk_control_operations(operation_id TEXT,run_id TEXT,kernel_store_id TEXT,orchestrator_store_id TEXT,orchestrator_incarnation TEXT,kernel_receipt TEXT,max_claims INTEGER,deadline_at REAL);
              CREATE TABLE sdk_revision_decisions(operation_id TEXT,run_id TEXT,source_revision INTEGER,source_epoch INTEGER,source_generation INTEGER,target_generation INTEGER,deployment TEXT,migration_version TEXT,application_projection_version TEXT,source_application_state TEXT,target_application_state TEXT,decision TEXT,kernel_install_receipt TEXT,orchestrator_install_receipt TEXT);
              CREATE TABLE sdk_control_authority_clock(singleton INTEGER PRIMARY KEY,observed_at REAL);
              CREATE TABLE sdk_storage_identity(singleton INTEGER,store_id TEXT,incarnation TEXT);
              CREATE TABLE sdk_managed_runs(run_id TEXT,control_state TEXT,control_epoch INTEGER,generation INTEGER,updated_at REAL);
              CREATE TABLE sdk_runs(run_id TEXT,revision INTEGER);
              CREATE TABLE sdk_run_revisions(run_id TEXT,revision INTEGER);
              CREATE TABLE sdk_retention_times(kind TEXT,identity TEXT,at REAL);
              CREATE TABLE sdk_run_items(run_id TEXT,section TEXT,item_key TEXT,value TEXT,UNIQUE(run_id,section,item_key));
              CREATE TABLE sdk_run_history(run_id TEXT,section TEXT,item_key TEXT,revision INTEGER,value TEXT);
              CREATE TABLE sdk_streamed_projection_pointers(run_id TEXT,revision INTEGER,pointer TEXT,PRIMARY KEY(run_id,revision));
              CREATE TABLE sdk_managed_control_transitions(run_id TEXT,epoch INTEGER,state TEXT,generation INTEGER,drain TEXT,mode TEXT,at REAL);
            ''')
            db.execute('INSERT INTO sdk_control_operations VALUES(?,?,?,?,?,?,?,?)', ('op','run','kernel','orch','inc',canonical({'claims_used':1}),5,100))
            db.execute('INSERT INTO sdk_revision_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)',('op','run',1,2,3,4,'{}','m','p',canonical(self.source),canonical(self.target),canonical(self.declaration),canonical(receipt)))
            db.execute("INSERT INTO sdk_storage_identity VALUES(1,'orch','inc')")
            db.execute("INSERT INTO sdk_managed_runs VALUES('run','paused',2,3,10)")
            db.execute("INSERT INTO sdk_runs VALUES('run',1)")
            db.execute("INSERT INTO sdk_run_revisions VALUES('run',1)")
            db.execute("INSERT INTO sdk_run_items VALUES('run','root','application_state','{\"a\":1}')")
        test = self
        class Kernel:
            def kernel_store_identity(self): return 'kernel'
            def get_run_control(self, run): return {'state':'paused','control_epoch':3,'generation':4}
            def observe_revision_authority(self, op): return {'store_id':'kernel','run_id':'run','decision_id':'op','generation':4,'control_epoch':3,'state':'paused','worker_principal':'worker','worker_expires_at':90,'revoked':False}
        class Host:
            kernel = Kernel()
            clock = staticmethod(lambda: 10)
            projection_verifier = staticmethod(lambda credential, storage: {'retained_immutable':True,'valid_json':True,'decision':test.claim})
            @contextmanager
            def _transaction(self):
                db = test.connect()
                try:
                    db.execute('BEGIN IMMEDIATE')
                    yield db
                    db.commit()
                finally: db.close()
            def _connect(self): return test.connect()
        self.host = Host()
        self.host.control_authorizer = ControlAuthorizer(self.host, lambda credential: {'principal':'p','permissions':[('run','install_revision')]})
        patcher = patch('dispatcher_sdk.orchestrator.streamed_install.check_control_lease', return_value={'lease_id':'lease','lease_fence':1})
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def install(self):
        return install_streamed_projection(self.host, 'op', storage=self.storage, credential='c', projection_credential='p', lease_credential='l')

    def test_install_and_replay_retains_history_pointer(self):
        first = self.install()
        self.assertEqual(self.install()['orchestrator_install_receipt'], first['orchestrator_install_receipt'])
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT value FROM sdk_run_history WHERE run_id='run' AND item_key='application_state' AND revision=2").fetchone()[0], '{"a":2}')
            self.assertEqual(db.execute("SELECT pointer FROM sdk_streamed_projection_pointers WHERE run_id='run' AND revision=2").fetchone()[0], STREAM_POINTER_PREFIX + canonical(self.target))
            self.assertEqual(tuple(db.execute("SELECT revision FROM sdk_runs").fetchone()), (2,))

    def test_actual_get_run_reads_noncanonical_materialized_json(self):
        from dispatcher_sdk.orchestrator.engine import Orchestrator
        with sqlite3.connect(self.storage.path) as db:
            db.execute("UPDATE projection_pages SET data=? WHERE stream_id='target'", (b'[ 1,2 ]',))
        with self.connect() as db:
            db.execute('CREATE TABLE sdk_disposed_runs(run_id TEXT)')
        self.install()
        actual = Orchestrator.__new__(Orchestrator)
        actual.db_path = str(self.path)
        actual.durability = 'full'
        self.assertEqual(actual.get_run('run')['application_state'], [1, 2])

    def test_direct_save_retains_stream_history_then_records_changed_json(self):
        from dispatcher_sdk.orchestrator.engine import Orchestrator
        from dispatcher_sdk.orchestrator.projection_stream import compare_projection_stream, iter_installed_projection
        with self.connect() as db:
            db.execute('CREATE TABLE sdk_disposed_runs(run_id TEXT)')
            db.execute("ALTER TABLE sdk_runs ADD COLUMN state TEXT DEFAULT 'running'")
        self.install()
        actual = Orchestrator.__new__(Orchestrator)
        actual.db_path, actual.durability = str(self.path), 'full'
        state = actual.get_run('run')
        state.update(state='running', revision=3)
        with self.connect() as db:
            actual._save(db, state, changes=set())
        self.assertEqual(actual.get_run('run')['application_state'], {'a':2})
        actual.projection_verifier = lambda credential, storage: {'retained_immutable':True, 'run_id':'run',
            'revision':3, 'pointer':self.target, 'orchestrator_store_id':'orch','orchestrator_incarnation':'inc'}
        self.assertEqual(b''.join(iter_installed_projection(actual, 'run', revision=3, storage=self.storage, credential='read')), b'{"a":2}')
        self.assertEqual(compare_projection_stream(actual, 'run', expected_revision=3, storage=self.storage,
            stream_id='target', expected_binding=self.target['binding'], source_read_credential='read')['total_bytes'], 7)
        state = actual.get_run('run')
        state.update(state='running', revision=4, application_state={'a':3})
        with self.connect() as db:
            actual._save(db, state, changes=set())
        self.assertEqual(actual.get_run('run')['application_state'], {'a':3})
        self.assertEqual(actual.get_run_at('run', 2)['application_state'], {'a':2})
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT value FROM sdk_run_history WHERE revision=4 AND item_key='application_state'").fetchone()[0], '{"a":3}')
        state = actual.get_run('run')
        state.update(state='running', revision=5, application_state={'a':'😊' * 75000})
        with self.connect() as db:
            actual._save(db, state, changes=set())
        raw = canonical(state['application_state']).encode('utf-8')
        self.storage.create('changed', total_bytes=len(raw), binding={'kind':'changed'})
        self.storage.append('changed', sequence=0, data=raw[:262144], complete=False)
        self.storage.append('changed', sequence=1, data=raw[262144:], complete=True)
        self.assertEqual(compare_projection_stream(actual, 'run', expected_revision=5, storage=self.storage,
            stream_id='changed', expected_binding={'kind':'changed'})['total_bytes'], len(raw))
        self.assertEqual(actual.get_run('run')['application_state'], state['application_state'])

    def test_install_with_actual_kernel_streamed_receipt(self):
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        page, envelope = {}, {}
        def verifier(credential):
            if credential == 'manager':
                return {'principal':'manager','expires_at':90,'permissions': [('run','kernel:manage_authority'),('run','kernel:pause')]}
            if credential == 'page':
                return {'principal':'manager','expires_at':90,'permissions':[('run','kernel:stage_revision')],'revision_page':dict(page)}
            if credential == 'decision':
                return {'principal':'manager','expires_at':90,'permissions':[('run','kernel:install_revision')],'decision':dict(envelope)}
            return {'principal':credential,'expires_at':90,'run_id':'run','generation':0 if credential == 'old' else 1,
                    'control_epoch':0 if credential == 'old' else 3,'permissions':[('run','kernel:worker')]}
        kernel = SQLiteKernel(self.path.parent / 'kernel.db', now=lambda:10, authority_verifier=verifier, worker_credential='manager')
        self.addCleanup(kernel.close)
        kernel.register_run_control('run', max_claims=5, deadline_at=100)
        kernel.protect_run_authority('run', generation=0, expected_epoch=0, worker_credential='old')
        with kernel._transaction() as (db, _):
            db.execute("UPDATE kernel_run_controls SET state='active' WHERE run_id='run'")
        barrier = kernel.prepare_control_pause('op','run',expected_epoch=0,generation=0)
        kernel.complete_control_pause('complete','op','run',expected_epoch=1,generation=0)
        page_number = 0
        while True:
            capture = kernel.capture_control_pause_page('op', expected_page=page_number)
            if capture['capture_complete']: break
            page_number += 1
        kid = kernel.kernel_store_identity()
        mappings = {}
        for kind, text in (('source_application_state','{"a":1}'),('target_application_state','{"a":2}')):
            page.clear()
            page.update(operation_id='op',barrier_operation_id='op',source_generation=0,decision_id='op',run_id='run',
                        kernel_store_id=kid,orchestrator_store_id='orch',orchestrator_incarnation='inc',
                        content_kind=kind,page_seq=0,total_bytes=7,chunk=text,complete=True,
                        lease_id='lease',lease_fence=1,lease_expires_at=90,lease_held=True)
            kernel.stage_revision_content_page('page', expected_page=dict(page))
            mappings[kind] = {'operation_id':'op','total_bytes':7,'lease_id':'lease','lease_fence':1}
        self.declaration['content_pages'] = mappings
        self.claim.update(kernel_store_id=kid,source_generation=0,declaration=self.declaration)
        envelope.update(decision_id='op',operation_id='op',barrier_operation_id='op',run_id='run',
                        orchestrator_store_id='orch',orchestrator_incarnation='inc',kernel_store_id=kid,
                        source_revision=1,source_generation=0,source_control_epoch=2,target_generation=1,
                        deployment={},revision={'v':2},source_application_state=None,target_application_state=None,
                        content_pages=mappings,migration_version='m',application_projection_version='p')
        receipt = kernel.install_revision_decision('decision',worker_credential='next',expected_decision=dict(envelope))
        self.host.kernel = kernel
        with self.connect() as db:
            db.execute('UPDATE sdk_control_operations SET kernel_store_id=?,kernel_receipt=?', (kid,canonical(barrier)))
            db.execute('UPDATE sdk_revision_decisions SET source_generation=0,target_generation=1,decision=?,kernel_install_receipt=?', (canonical(self.declaration),canonical(receipt)))
            db.execute('UPDATE sdk_managed_runs SET generation=0')
        result = self.install()
        self.assertEqual(json.loads(result['orchestrator_install_receipt'])['generation'], 1)
        self.assertEqual(self.install()['orchestrator_install_receipt'], result['orchestrator_install_receipt'])

    def test_missing_target_is_atomic(self):
        with sqlite3.connect(self.storage.path) as db:
            db.execute("DELETE FROM projection_pages WHERE stream_id='target'")
        with self.assertRaises(Exception): self.install()
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT revision FROM sdk_runs').fetchone()[0], 1)
            self.assertIsNone(db.execute('SELECT orchestrator_install_receipt FROM sdk_revision_decisions').fetchone()[0])

    def test_source_mismatch_and_verifier_denial_fail_closed(self):
        self.host.projection_verifier = lambda *_: {'retained_immutable':False}
        with self.assertRaises(OrchestrationError): self.install()
        self.host.projection_verifier = lambda *_: {'retained_immutable':True,'valid_json':True,'decision':self.claim}
        with self.connect() as db: db.execute("UPDATE sdk_run_items SET value='{\"a\":9}'")
        with self.assertRaises(OrchestrationError): self.install()

    def test_invalid_json_and_kernel_receipt_are_rejected(self):
        with sqlite3.connect(self.storage.path) as db:
            db.execute("UPDATE projection_pages SET data=? WHERE stream_id='target'", (b'{bad  }',))
        with self.assertRaises(OrchestrationError): self.install()
        with sqlite3.connect(self.storage.path) as db:
            db.execute("UPDATE projection_pages SET data=? WHERE stream_id='target'", (b'{\"a\":2}',))
        with self.connect() as db:
            row = json.loads(db.execute('SELECT kernel_install_receipt FROM sdk_revision_decisions').fetchone()[0])
            row['decision']['target_generation'] = 5
            db.execute('UPDATE sdk_revision_decisions SET kernel_install_receipt=?', (canonical(row),))
        with self.assertRaises(OrchestrationError): self.install()
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT revision FROM sdk_runs').fetchone()[0], 1)

    def test_late_lease_failure_rolls_back_installation(self):
        with patch('dispatcher_sdk.orchestrator.streamed_install.check_control_lease', side_effect=[
                {'lease_id':'lease','lease_fence':1}, {'lease_id':'lease','lease_fence':1},
                OrchestrationError('expired')]):
            with self.assertRaises(OrchestrationError): self.install()
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT revision FROM sdk_runs').fetchone()[0], 1)
            self.assertIsNone(db.execute('SELECT orchestrator_install_receipt FROM sdk_revision_decisions').fetchone()[0])
