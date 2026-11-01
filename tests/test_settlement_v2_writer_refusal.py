"""Explicit v2 settlement selection cannot admit a writer or modify evidence."""
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.children import _Store
from dispatcher_sdk.execution_kernel.settlement import SettlementBindingError, SettlementJournal, _SCHEMA
from tests.test_supervisor_outcome_handoff import supervisor_with_short_work_budget


class SettlementV2WriterRefusalTests(unittest.TestCase):
    def test_explicit_v2_rejected_by_runtime_child_and_supervisor_writers(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('dispatcher_sdk.execution_kernel.runtime.registry_revision', return_value='host-supplied'), \
             patch('dispatcher_sdk.execution_kernel.runtime.handler_revision', return_value='host-supplied'):
            root = Path(directory)
            kernel_path = root / 'kernel.sqlite'
            runtime = Kernel.open_sqlite(kernel_path, {}, isolation_mode='thread')
            source = runtime.settlement_storage['source_id']
            runtime.close()
            path = root / 'v2.sqlite'
            with sqlite3.connect(path) as db:
                for statement in _SCHEMA[:-1]:
                    db.execute(statement)
                db.execute('INSERT INTO settlement_meta VALUES(1,2,?,?)', (source, str(kernel_path)))
                db.execute("INSERT INTO settlement_notes(note_id,execution_id,attempt,fence,phase,evidence_json,created_at) "
                           "VALUES('old','execution',2,3,'supervisor_spawn_intent','{}',1)")
                db.commit()
                before = list(db.iterdump())
            binding = {'path': str(path), 'kernel_path': str(kernel_path), 'source_id': source}
            with self.assertRaises(SettlementBindingError):
                SettlementJournal.open_existing(**binding, timeout_seconds=1)
            readonly = SettlementJournal.open_readonly(**binding, timeout_seconds=1)
            self.assertEqual(readonly.inspect_notes('execution', timeout_seconds=1)['notes'][0]['note_id'], 'old')
            with self.assertRaises(SettlementBindingError):
                Kernel.open_sqlite(kernel_path, {}, isolation_mode='thread', settlement_journal_path=str(path))
            child = _Store(SimpleNamespace(source_id=source, kernel_path=str(kernel_path)),
                           {**binding, 'available': True})
            with self.assertRaises(SettlementBindingError):
                child._facts(writer=True, timeout_seconds=1)
            with sqlite3.connect(path) as db:
                self.assertEqual(list(db.iterdump()), before)
            if not hasattr(os, 'fork'):
                self.skipTest('supervisor writer observation requires POSIX fork')
            ctx = multiprocessing.get_context('fork')
            receiver, sender = ctx.Pipe(duplex=False)
            proc = ctx.Process(target=supervisor_with_short_work_budget, args=(sender, binding))
            proc.start()
            sender.close()
            packets = []
            try:
                while receiver.poll(3):
                    try:
                        packets.append(json.loads(receiver.recv_bytes()))
                    except EOFError:
                        break
                proc.join(3)
                if proc.is_alive():
                    proc.terminate()
                    proc.join()
                    self.fail('supervisor did not exit')
                self.assertEqual(proc.exitcode, 0)
                completed = next(packet for packet in packets if packet.get('kind') == 'handler_completed')
                self.assertEqual(completed['outcome_handoff']['state'], 'unknown')
                self.assertEqual(completed['outcome_handoff']['reason'], 'journal_write_failed')
                with sqlite3.connect(path) as db:
                    self.assertEqual(list(db.iterdump()), before)
            finally:
                receiver.close()
