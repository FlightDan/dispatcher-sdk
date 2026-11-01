"""Paused installation of a previously committed streamed revision.

The host must retain immutable projection storage and serialize all Kernel and
Orchestrator control writers, including revocation, through the final commit.
Kernel observations are non-atomic with the local SQLite transaction.
"""
from __future__ import annotations

import codecs
import json
import math
import tempfile

from .contracts import OrchestrationError, RevisionConflict, canonical, identifier
from .control_authorization import ControlAuthorizer
from .control_lease import check_control_lease, observe_control_clock
from .projection_json import _Validator
from .projection_storage import MAX_STREAM_BYTES, ProjectionStorage
from .projection_stream import STREAM_POINTER_PREFIX, compare_projection_stream


def install_streamed_projection(orchestrator, operation_id, *, storage, credential,
                                projection_credential, lease_credential, delegation_id=None,
                                source_read_credential=None):
    """Install an exact committed stream pointer, leaving both participants paused.

    Target content is exhausted and strictly validated before the local CAS.
    Retention/lease verifier claims are host trust boundaries, not SDK locks on
    external storage or the Kernel. No activation or resume is performed.
    """
    identifier(operation_id, 'operation_id')
    if type(storage) is not ProjectionStorage or not callable(getattr(orchestrator, 'projection_verifier', None)):
        raise OrchestrationError('projection storage and verifier are required')
    authorizer = orchestrator.control_authorizer
    if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not orchestrator:
        raise OrchestrationError('trusted control authorizer is required')
    participant = orchestrator.kernel
    identity_reader = getattr(participant, 'kernel_store_identity', None)
    gate_reader = getattr(participant, 'get_run_control', None)
    authority_reader = getattr(participant, 'observe_revision_authority', None)
    if not all(callable(f) for f in (identity_reader, gate_reader, authority_reader)):
        raise OrchestrationError('Kernel observation is unavailable')
    observe_control_clock(orchestrator)
    verified = authorizer.verify(credential)
    with orchestrator._transaction() as db:
        operation = db.execute('SELECT * FROM sdk_control_operations WHERE operation_id=?', (operation_id,)).fetchone()
        decision = db.execute('SELECT * FROM sdk_revision_decisions WHERE operation_id=?', (operation_id,)).fetchone()
        if operation is None or decision is None or decision['kernel_install_receipt'] is None:
            raise OrchestrationError('committed decision and Kernel receipt are required')
        operation, decision = dict(operation), dict(decision)
        run_id = operation['run_id']
        authorizer.check_in_transaction(db, verified, run_id, 'install_revision', delegation_id)
        expected = {'operation_id': operation_id, 'run_id': run_id, 'kernel_store_id': operation['kernel_store_id'],
                    'orchestrator_store_id': operation['orchestrator_store_id'], 'orchestrator_incarnation': operation['orchestrator_incarnation']}
        lease = check_control_lease(orchestrator, db, lease_credential, expected)
    declaration = json.loads(decision['decision'])
    source = json.loads(decision['source_application_state'])
    target = json.loads(decision['target_application_state'])
    receipt = json.loads(decision['kernel_install_receipt'])
    if (type(declaration) is not dict or declaration.get('stream_version') != 1 or
        canonical(declaration.get('source_pointer')) != canonical(source) or
        canonical(declaration.get('target_pointer')) != canonical(target) or
        decision['run_id'] != run_id or decision['target_generation'] != decision['source_generation'] + 1):
        raise OrchestrationError('streamed decision is invalid')
    required_pointer = {'stream_id', 'binding', 'total_bytes', 'store_id', 'incarnation'}
    for pointer in (source, target):
        if (type(pointer) is not dict or set(pointer) != required_pointer or type(pointer['binding']) is not dict or
                type(pointer['total_bytes']) is not int or not 1 <= pointer['total_bytes'] <= MAX_STREAM_BYTES or
                any(type(pointer[key]) is not str or not pointer[key].strip() or len(pointer[key].encode('utf-8')) > 4096
                    for key in ('stream_id', 'store_id', 'incarnation')) or
                len(canonical(pointer).encode('utf-8')) > 65536):
            raise OrchestrationError('projection pointer is invalid')
    envelope = {'decision_id': operation_id, 'operation_id': operation_id, 'barrier_operation_id': operation_id,
                'run_id': run_id, 'orchestrator_store_id': expected['orchestrator_store_id'],
                'orchestrator_incarnation': expected['orchestrator_incarnation'], 'kernel_store_id': expected['kernel_store_id'],
                'source_revision': decision['source_revision'], 'source_generation': decision['source_generation'],
                'source_control_epoch': decision['source_epoch'], 'target_generation': decision['target_generation'],
                'deployment': json.loads(decision['deployment']), 'revision': declaration['revision'],
                'source_application_state': None, 'target_application_state': None,
                'content_pages': declaration['content_pages'], 'migration_version': decision['migration_version'],
                'application_projection_version': decision['application_projection_version']}
    barrier = json.loads(operation['kernel_receipt'])
    if (type(receipt) is not dict or receipt.get('kind') != 'paused_revision_install' or
            canonical(receipt.get('decision')) != canonical(envelope) or receipt.get('activation') != 'closed' or
            receipt.get('target_control_epoch') != decision['source_epoch'] + 1 or
            (receipt.get('claims_used'), receipt.get('max_claims'), receipt.get('deadline_at')) !=
            (barrier.get('claims_used'), operation['max_claims'], operation['deadline_at'])):
        raise OrchestrationError('Kernel revision receipt differs from streamed decision')
    expected_claim = {**expected, 'source_revision': decision['source_revision'], 'source_epoch': decision['source_epoch'],
                      'source_generation': decision['source_generation'], 'declaration': declaration,
                      'lease_id': lease['lease_id'], 'lease_fence': lease['lease_fence']}
    def attest():
        try:
            claim = orchestrator.projection_verifier(projection_credential, storage)
            if (type(claim) is not dict or claim.get('retained_immutable') is not True or
                    claim.get('valid_json') is not True or canonical(claim.get('decision')) != canonical(expected_claim)):
                raise ValueError()
        except Exception:
            raise OrchestrationError('host projection retention is unavailable') from None
    def observe_kernel():
        authority, gate = authority_reader(operation_id), gate_reader(run_id)
        if (orchestrator.kernel is not participant or identity_reader() != expected['kernel_store_id'] or
            type(authority) is not dict or type(gate) is not dict or
            (authority.get('store_id'), authority.get('run_id'), authority.get('decision_id'), authority.get('generation'),
             authority.get('control_epoch'), authority.get('state'), authority.get('worker_principal'), authority.get('worker_expires_at'), authority.get('revoked')) !=
            (expected['kernel_store_id'], run_id, operation_id, decision['target_generation'], decision['source_epoch'] + 1,
             'paused', receipt.get('worker_principal'), receipt.get('worker_expires_at'), False) or
            (gate.get('state'), gate.get('control_epoch'), gate.get('generation')) !=
            ('paused', decision['source_epoch'] + 1, decision['target_generation'])):
            raise OrchestrationError('Kernel installed authority is unknown or changed')
        return authority
    attest()
    if decision['orchestrator_install_receipt'] is None:
        comparison = compare_projection_stream(orchestrator, run_id, expected_revision=decision['source_revision'], storage=storage,
                                  stream_id=source['stream_id'], expected_binding=source['binding'],
                                  source_read_credential=source_read_credential)
        if ((comparison['store_id'], comparison['incarnation'], comparison['total_bytes']) !=
                (source['store_id'], source['incarnation'], source['total_bytes'])):
            raise OrchestrationError('source projection storage differs')
    # Validate each bounded page, including UTF-8 characters split across pages.
    validator, decoder = _Validator(64), codecs.getincrementaldecoder('utf-8')('strict')
    cursor, size = -1, 0
    payload = tempfile.TemporaryFile()
    try:
        while True:
            attest()
            batch = storage.read(target['stream_id'], after=cursor, limit=1)
            if (not batch['complete'] or batch['stored_bytes'] != target['total_bytes'] or
                batch['total_bytes'] != target['total_bytes'] or
                (batch['store_id'], batch['incarnation']) != (target['store_id'], target['incarnation']) or
                canonical(batch['binding']) != canonical(target['binding']) or len(batch['pages']) != 1):
                raise OrchestrationError('target stream is incomplete or changed')
            page = batch['pages'][0]
            if page['complete'] != (not batch['has_more']):
                raise OrchestrationError('target stream terminal marker differs')
            size += len(page['data'])
            if size > target['total_bytes']:
                raise OrchestrationError('target stream exceeds its size')
            validator.feed(decoder.decode(page['data']))
            payload.write(page['data'])
            cursor = batch['cursor']
            if not batch['has_more']:
                break
        validator.feed(decoder.decode(b'', final=True))
        validator.finish()
        payload.seek(0)
        # The public Run API loads JSON values in memory. Materialization is
        # explicitly limited by ProjectionStorage's 64 MiB stream bound.
        materialized = payload.read().decode('utf-8')
    except (UnicodeError, ValueError) as exc:
        raise OrchestrationError('target stream JSON is invalid') from exc
    finally:
        payload.close()
    if size != target['total_bytes']:
        raise OrchestrationError('target stream is incomplete')
    attest()
    authority = observe_kernel()
    observe_control_clock(orchestrator)
    verified = authorizer.verify(credential)
    with orchestrator._transaction() as db:
        authorizer.check_in_transaction(db, verified, run_id, 'install_revision', delegation_id)
        check_control_lease(orchestrator, db, lease_credential, {**expected, 'lease_id': lease['lease_id'], 'lease_fence': lease['lease_fence']})
        attest()
        current = db.execute('SELECT * FROM sdk_revision_decisions WHERE operation_id=?', (operation_id,)).fetchone()
        current_op = db.execute('SELECT * FROM sdk_control_operations WHERE operation_id=?', (operation_id,)).fetchone()
        identity = db.execute('SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1').fetchone()
        control = db.execute('SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?', (run_id,)).fetchone()
        run = db.execute('SELECT revision FROM sdk_runs WHERE run_id=?', (run_id,)).fetchone()
        if (current is None or current_op is None or dict(current_op) != operation or
                any(current[key] != decision[key] for key in decision if key != 'orchestrator_install_receipt') or
                identity is None or tuple(identity) != (expected['orchestrator_store_id'], expected['orchestrator_incarnation']) or
                orchestrator.kernel is not participant or identity_reader() != expected['kernel_store_id']):
            raise RevisionConflict('streamed installation decision changed')
        if current['orchestrator_install_receipt'] is not None:
            saved = json.loads(current['orchestrator_install_receipt'])
            history = db.execute("SELECT value FROM sdk_run_history WHERE run_id=? AND section='root' AND item_key='application_state' AND revision=?", (run_id, decision['source_revision'] + 1)).fetchone()
            pointer_row = db.execute('SELECT pointer FROM sdk_streamed_projection_pointers WHERE run_id=? AND revision=?', (run_id, decision['source_revision'] + 1)).fetchone()
            if (type(saved) is not dict or saved.get('operation_id') != operation_id or
                    saved.get('run_id') != run_id or saved.get('revision') != decision['source_revision'] + 1 or
                    saved.get('generation') != decision['target_generation'] or
                    history is None or history[0] != materialized or pointer_row is None or
                    pointer_row[0] != STREAM_POINTER_PREFIX + canonical(target)):
                raise RevisionConflict('installed projection receipt differs')
            return dict(current)
        if (run is None or run[0] != decision['source_revision'] or control is None or
            tuple(control) != ('paused', decision['source_epoch'], decision['source_generation'])):
            raise RevisionConflict('streamed installation source changed')
        revision, epoch = decision['source_revision'] + 1, decision['source_epoch'] + 1
        pointer = STREAM_POINTER_PREFIX + canonical(target)
        db.execute('UPDATE sdk_runs SET revision=? WHERE run_id=?', (revision, run_id))
        db.execute('INSERT INTO sdk_run_revisions VALUES(?,?)', (run_id, revision))
        db.execute("INSERT INTO sdk_retention_times VALUES('revision',?,(julianday('now')-2440587.5)*86400.0)", (canonical([run_id, revision]),))
        for key, value in (('application_state', materialized), ('generation', canonical(decision['target_generation']))):
            db.execute("INSERT INTO sdk_run_items VALUES(?,'root',?,?) ON CONFLICT(run_id,section,item_key) DO UPDATE SET value=excluded.value", (run_id, key, value))
            db.execute("INSERT INTO sdk_run_history VALUES(?,'root',?,?,?)", (run_id, key, revision, value))
        db.execute('INSERT INTO sdk_streamed_projection_pointers VALUES(?,?,?)', (run_id, revision, pointer))
        now = float(orchestrator.clock())
        if not math.isfinite(now):
            raise OrchestrationError('installation clock is unknown')
        db.execute('UPDATE sdk_managed_runs SET generation=?,control_epoch=?,updated_at=? WHERE run_id=?', (decision['target_generation'], epoch, now, run_id))
        db.execute('INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)', (run_id, epoch, 'paused', decision['target_generation'], '[]', None, now))
        result = {'operation_id': operation_id, 'run_id': run_id, 'revision': revision, 'generation': decision['target_generation'],
                  'control_epoch': epoch, 'state': 'paused', 'installed_at': now, 'kernel_observation': 'non_atomic',
                  'kernel_authority_observed_at': authority.get('observed_at'), 'cleanup': 'unknown'}
        db.execute('UPDATE sdk_revision_decisions SET orchestrator_install_receipt=? WHERE operation_id=?', (canonical(result), operation_id))
        check_control_lease(orchestrator, db, lease_credential, {**expected, 'lease_id': lease['lease_id'], 'lease_fence': lease['lease_fence']})
        return dict(db.execute('SELECT * FROM sdk_revision_decisions WHERE operation_id=?', (operation_id,)).fetchone())
