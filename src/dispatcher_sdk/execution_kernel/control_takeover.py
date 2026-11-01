"""Host-authenticated control-lease handoff; old participant receipts stay immutable."""
from __future__ import annotations

import json

from ._sqlite_base import encode_json
from .errors import CASConflictError, StorageIsolationError

_TAKEOVER_FIELDS = {'takeover_id', 'phase', 'operation_id', 'run_id', 'kernel_store_id',
                    'orchestrator_store_id', 'orchestrator_incarnation', 'generation', 'control_epoch',
                    'original_decision', 'original_receipt', 'previous_lease_id', 'previous_fence',
                    'new_lease_id', 'new_fence', 'lease_expires_at', 'lease_held', 'old_holder_excluded',
                    'max_claims', 'claims_used', 'deadline_at'}


class ControlTakeoverMixin:
    @staticmethod
    def _verify_historical_control_decision(connection, phase, original, decision):
        """Check a receipt's issuing lease against its own durable handoff."""
        if type(decision) is not dict:
            return False
        excluded = {'lease_id', 'lease_fence', 'lease_expires_at'}
        if ({k: v for k, v in original.items() if k not in excluded} !=
                {k: v for k, v in decision.items() if k not in excluded}):
            return False
        fence, lease_id = decision.get('lease_fence'), decision.get('lease_id')
        if type(fence) is not int or type(lease_id) is not str:
            return False
        row = connection.execute(
            'SELECT claim_json FROM kernel_control_takeovers WHERE operation_id=? AND new_fence=?',
            (original['operation_id'], fence),
        ).fetchone()
        if row is None:
            return False
        claim = json.loads(row[0])
        return (claim['phase'] == phase and claim['new_lease_id'] == lease_id
                and claim['new_fence'] == fence and claim['original_decision'] == original)

    @staticmethod
    def _verify_effective_control_decision(connection, phase, decision):
        row = connection.execute(
            'SELECT claim_json FROM kernel_control_takeovers WHERE operation_id=? ORDER BY new_fence DESC LIMIT 1',
            (decision['operation_id'],),
        ).fetchone()
        if row is None:
            return False
        claim = json.loads(row[0])
        excluded = {'lease_id', 'lease_fence', 'lease_expires_at'}
        original = {k: v for k, v in claim['original_decision'].items() if k not in excluded}
        requested = {k: v for k, v in decision.items() if k not in excluded}
        if (claim['phase'] != phase or encode_json(original) != encode_json(requested)
                or (decision['lease_id'], decision['lease_fence']) != (claim['new_lease_id'], claim['new_fence'])):
            raise CASConflictError('control decision differs from authenticated takeover')
        return True

    @staticmethod
    def _effective_takeover_binding(connection, phase, operation_id, original_lease_id, original_fence):
        row = connection.execute(
            "SELECT claim_json FROM kernel_control_takeovers WHERE operation_id=? ORDER BY new_fence DESC LIMIT 1",
            (operation_id,),
        ).fetchone()
        if row is None:
            return original_lease_id, original_fence
        claim = json.loads(row[0])
        if claim['phase'] != phase:
            raise CASConflictError('control takeover phase differs')
        return claim['new_lease_id'], claim['new_fence']

    @classmethod
    def _effective_control_lease(cls, connection, decision):
        lease_id, fence = cls._effective_takeover_binding(connection, 'resume', decision['operation_id'],
                                                         decision['lease_id'], decision['lease_fence'])
        return (lease_id, fence, decision['operation_id'], decision['orchestrator_store_id'],
                decision['orchestrator_incarnation'], decision['kernel_store_id'], decision['run_id'],
                decision['generation'], decision['target_control_epoch'])

    def _takeover_proof(self, credential, claim, timestamp):
        try:
            verified = self._authority_verifier(credential)
            expiry = self._number(verified['expires_at'], 'authority expiry', minimum=0.0)
            principal = verified['principal']
            if (type(principal) is not str or not principal.strip() or len(principal.encode()) > 4096
                    or expiry <= timestamp or claim['lease_expires_at'] <= timestamp
                    or encode_json(verified['control_takeover']) != encode_json(claim)
                    or not any(tuple(p) == (claim['run_id'], 'kernel:takeover_control') for p in verified['permissions'])):
                raise ValueError('invalid takeover proof')
            return principal, expiry
        except Exception:
            raise StorageIsolationError('host did not authorize control takeover') from None

    def takeover_control_lease(self, credential, *, expected_takeover):
        """Record an exact host-verified takeover; caller must hold host exclusion through commit.

        The host attests original intent, old-holder exclusion and its currently held new lease.
        This receipt alone does not authenticate an Orchestrator active receipt or admit work.
        """
        try:
            c = json.loads(encode_json(expected_takeover))
            if (type(c) is not dict or set(c) != _TAKEOVER_FIELDS or len(encode_json(c).encode()) > 1048576
                    or c['phase'] not in ('activation', 'resume')
                    or any(type(c[k]) is not str or not c[k].strip() or len(c[k].encode()) > 4096
                           for k in ('takeover_id', 'operation_id', 'run_id', 'kernel_store_id',
                                     'orchestrator_store_id', 'orchestrator_incarnation', 'previous_lease_id', 'new_lease_id'))
                    or any(type(c[k]) is not int or not 0 <= c[k] < (1 << 63)
                           for k in ('generation', 'control_epoch', 'previous_fence', 'new_fence', 'max_claims', 'claims_used'))
                    or c['new_fence'] <= c['previous_fence'] or c['claims_used'] > c['max_claims']
                    or c['lease_held'] is not True or c['old_holder_excluded'] is not True
                    or type(c['original_decision']) is not dict
                    or (c['original_receipt'] is not None and type(c['original_receipt']) is not dict)):
                raise ValueError('invalid takeover')
            self._number(c['lease_expires_at'], 'lease expiry', minimum=0.0)
            self._number(c['deadline_at'], 'deadline', minimum=0.0)
        except Exception:
            raise ValueError('invalid control takeover') from None
        d = c['original_decision']
        try:
            if any(d[k] != c[k] for k in ('operation_id', 'run_id', 'kernel_store_id', 'orchestrator_store_id',
                                           'orchestrator_incarnation', 'generation')):
                raise ValueError('identity differs')
            if d['expected_control_epoch'] != c['control_epoch']:
                raise ValueError('epoch differs')
            if c['phase'] == 'resume' and d['target_control_epoch'] != c['control_epoch'] + 1:
                raise ValueError('target epoch differs')
        except Exception:
            raise ValueError('invalid takeover original decision') from None
        with self._transaction() as (connection, timestamp):
            proof = self._takeover_proof(credential, c, timestamp)
            identity = connection.execute('SELECT store_id FROM kernel_store_identity WHERE singleton=1').fetchone()
            if identity is None or identity[0] != c['kernel_store_id']:
                raise CASConflictError('takeover participant identity differs')
            previous = connection.execute('SELECT claim_json,receipt_json FROM kernel_control_takeovers WHERE takeover_id=?', (c['takeover_id'],)).fetchone()
            if previous is not None:
                original = json.loads(previous[0])
                if ({k: v for k, v in original.items() if k != 'lease_expires_at'} !=
                        {k: v for k, v in c.items() if k != 'lease_expires_at'}):
                    raise CASConflictError('takeover replay differs')
                # A receipt is a historical fact, not a new admission grant.
                # Business progress and later fences do not rewrite it.
                now = self._advance_clock(connection)
                if self._takeover_proof(credential, c, now) != proof or min(proof[1], c['lease_expires_at']) <= self._advance_clock(connection):
                    raise StorageIsolationError('control takeover authority expired')
                return json.loads(previous[1])
            control = connection.execute('SELECT generation,control_epoch,state,max_claims,claims_used,deadline_at FROM kernel_run_controls WHERE run_id=?', (c['run_id'],)).fetchone()
            installed = connection.execute('SELECT receipt_json FROM kernel_revision_installs WHERE decision_id=? AND run_id=?', (d['decision_id'], c['run_id'])).fetchone()
            authority = connection.execute('SELECT generation,control_epoch,principal,expires_at,revoked_at FROM kernel_run_authorities WHERE run_id=?', (c['run_id'],)).fetchone()
            if identity is None or identity[0] != c['kernel_store_id'] or installed is None or control is None or authority is None:
                raise CASConflictError('takeover participant facts unavailable')
            install = json.loads(installed[0])
            if (encode_json(install) != encode_json(d['kernel_install_receipt'])
                    or any(install['decision'][k] != d[k] for k in ('kernel_store_id', 'orchestrator_store_id', 'orchestrator_incarnation'))
                    or any(install['decision'][k] != d[k] for k in ('run_id', 'barrier_operation_id', 'decision_id'))
                    or install['decision']['target_generation'] != c['generation']
                    or tuple(control[3:]) != (c['max_claims'], c['claims_used'], c['deadline_at'])
                    or authority[0] != c['generation'] or authority[4] is not None or authority[3] <= timestamp):
                raise CASConflictError('takeover installation, budget or authority differs')
            if connection.execute("SELECT 1 FROM kernel_control_pause_receipts WHERE run_id=? AND json_extract(receipt_json,'$.kind')='cancellation_fence' LIMIT 1", (c['run_id'],)).fetchone():
                raise CASConflictError('takeover Run is cancelled')
            completion = connection.execute('SELECT receipt_json FROM kernel_control_pause_receipts WHERE operation_id=? AND run_id=?', (d['completion_operation_id'], c['run_id'])).fetchone()
            if completion is None or (json.loads(completion[0]).get('kind'), json.loads(completion[0]).get('barrier_operation_id')) != ('local_paused', d['barrier_operation_id']):
                raise CASConflictError('takeover pause completion differs')
            if connection.execute("SELECT 1 FROM kernel_control_pause_receipts b WHERE b.run_id=? "
                    "AND b.operation_id NOT IN (?,?) AND NOT EXISTS (SELECT 1 FROM kernel_resume_receipts r "
                    "WHERE r.run_id=b.run_id AND b.operation_id IN (r.barrier_operation_id,r.completion_operation_id)) LIMIT 1",
                    (c['run_id'], d['barrier_operation_id'], d['completion_operation_id'])).fetchone():
                raise CASConflictError('another control barrier is unresolved')
            table = 'kernel_activation_receipts' if c['phase'] == 'activation' else 'kernel_resume_receipts'
            existing = connection.execute(f'SELECT receipt_json FROM {table} WHERE operation_id=? AND run_id=?', (c['operation_id'], c['run_id'])).fetchone()
            prior_handoff = connection.execute('SELECT claim_json FROM kernel_control_takeovers WHERE operation_id=? ORDER BY new_fence DESC LIMIT 1', (c['operation_id'],)).fetchone()
            existing_receipt = None if existing is None else json.loads(existing[0])
            if existing_receipt != c['original_receipt']:
                # A handoff of an absent participant may itself be followed by
                # the exact operation under the new lease before replay.
                if c['original_receipt'] is not None or prior_handoff is None or existing_receipt is None:
                    raise CASConflictError('takeover original participant receipt differs')
                if not self._verify_historical_control_decision(connection, c['phase'], d, existing_receipt.get('decision', {})):
                    raise CASConflictError('takeover participant receipt has no authenticated issuing lease')
            if c['original_receipt'] is not None and c['original_receipt'].get('decision') != d:
                receipt_decision = c['original_receipt'].get('decision', {})
                same_renewal = (isinstance(receipt_decision, dict) and
                    {k: v for k, v in receipt_decision.items() if k != 'lease_expires_at'} ==
                    {k: v for k, v in d.items() if k != 'lease_expires_at'})
                if not same_renewal and (prior_handoff is None or not self._verify_historical_control_decision(connection, c['phase'], d, receipt_decision)):
                    raise CASConflictError('takeover original receipt decision differs')
            if c['phase'] == 'resume':
                activation = connection.execute('SELECT receipt_json FROM kernel_activation_receipts WHERE operation_id=? AND run_id=?', (d['activation_operation_id'], c['run_id'])).fetchone()
                if activation is None or json.loads(activation[0]) != d['activation_receipt']:
                    raise CASConflictError('takeover activation differs')
                activated = json.loads(activation[0])['decision']
                if any(encode_json(activated[k]) != encode_json(d[k]) for k in (
                        'run_id', 'decision_id', 'barrier_operation_id', 'completion_operation_id',
                        'kernel_store_id', 'orchestrator_store_id', 'orchestrator_incarnation',
                        'generation', 'expected_control_epoch', 'orchestrator_install_receipt', 'kernel_install_receipt')):
                    raise CASConflictError('takeover activation decision differs')
                binding = self._effective_takeover_binding(connection, 'activation', d['activation_operation_id'],
                                                           activated['lease_id'], activated['lease_fence'])
                if binding != (d['lease_id'], d['lease_fence']):
                    raise CASConflictError('takeover activation lease differs')
                policy = connection.execute('SELECT policy_json FROM kernel_budget_policies WHERE run_id=? AND generation=?',
                                            (c['run_id'], c['generation'])).fetchone()
                if policy is None or json.loads(policy[0]).get('decision_id') != d['decision_id']:
                    raise CASConflictError('takeover budget policy differs')
            expected_state = ('active', c['control_epoch'] + 1) if c['phase'] == 'resume' and existing else ('paused', c['control_epoch'])
            if (control[0], control[2], control[1]) != (c['generation'], *expected_state) or authority[1] != expected_state[1]:
                raise CASConflictError('takeover control state differs')
            if c['phase'] == 'activation' or existing is None:
                if (authority[2], authority[3]) != (install['worker_principal'], install['worker_expires_at']):
                    raise CASConflictError('takeover worker authority differs')
            else:
                if (authority[2], authority[3]) != (existing_receipt['worker_principal'], existing_receipt['worker_expires_at']) or self._has_unresolved_control_barrier(connection, c['run_id']):
                    raise CASConflictError('takeover resumed authority differs')
            previous = connection.execute('SELECT claim_json,receipt_json FROM kernel_control_takeovers WHERE takeover_id=?', (c['takeover_id'],)).fetchone()
            effective = self._effective_takeover_binding(connection, c['phase'], c['operation_id'], d['lease_id'], d['lease_fence'])
            latest = connection.execute('SELECT claim_json FROM kernel_control_takeovers WHERE run_id=? ORDER BY new_fence DESC LIMIT 1', (c['run_id'],)).fetchone()
            latest_claim = None if latest is None else json.loads(latest[0])
            if previous:
                if (json.loads(previous[0]) != c or effective != (c['new_lease_id'], c['new_fence'])
                        or latest_claim['takeover_id'] != c['takeover_id']):
                    raise CASConflictError('takeover replay differs or was superseded')
                receipt = json.loads(previous[1])
            else:
                if (effective != (c['previous_lease_id'], c['previous_fence'])
                        or (latest_claim is not None and latest_claim['operation_id'] == c['operation_id'] and
                            (latest_claim['original_decision'] != c['original_decision'] or
                             (latest_claim['original_receipt'] != c['original_receipt'] and
                              not (latest_claim['original_receipt'] is None and c['original_receipt'] is not None
                                   and existing_receipt == c['original_receipt'] and
                                   self._verify_historical_control_decision(connection, c['phase'], d, existing_receipt['decision'])))))
                        or (latest_claim is not None and
                            (effective[1] < latest_claim['new_fence'] or
                             (effective[1] == latest_claim['new_fence'] and
                              effective[0] != latest_claim['new_lease_id'])))):
                    raise CASConflictError('takeover previous lease differs')
                receipt = {'kind': 'control_lease_takeover', 'claim': c, 'recorded_at': timestamp}
                connection.execute('INSERT INTO kernel_control_takeovers VALUES(?,?,?,?,?,?)', (c['run_id'], c['operation_id'], c['new_fence'], c['takeover_id'], encode_json(c), encode_json(receipt)))
            now = self._advance_clock(connection)
            if self._takeover_proof(credential, c, now) != proof or min(proof[1], c['lease_expires_at'], authority[3]) <= self._advance_clock(connection):
                raise StorageIsolationError('control takeover authority expired')
            return receipt

    def inspect_control_participant_receipt(self, credential, *, expected_inspection):
        """Return one bounded exact participant receipt under host-held control authority."""
        fields = {'phase', 'operation_id', 'run_id', 'kernel_store_id', 'orchestrator_store_id',
                  'orchestrator_incarnation', 'lease_id', 'lease_fence', 'lease_expires_at', 'lease_held'}
        try:
            claim = json.loads(encode_json(expected_inspection))
            if (type(claim) is not dict or set(claim) != fields or claim['phase'] not in ('activation', 'resume')
                    or any(type(claim[k]) is not str or not claim[k].strip() or len(claim[k].encode()) > 4096
                           for k in ('operation_id', 'run_id', 'kernel_store_id', 'orchestrator_store_id', 'orchestrator_incarnation', 'lease_id'))
                    or type(claim['lease_fence']) is not int or not 0 <= claim['lease_fence'] < (1 << 63)
                    or claim['lease_held'] is not True):
                raise ValueError('invalid inspection')
            self._number(claim['lease_expires_at'], 'lease expiry', minimum=0.0)
        except Exception:
            raise ValueError('invalid control receipt inspection') from None
        def verify(timestamp):
            try:
                verified = self._authority_verifier(credential)
                principal = verified['principal']
                expiry = self._number(verified['expires_at'], 'authority expiry', minimum=0.0)
                if (type(principal) is not str or not principal.strip() or len(principal.encode()) > 4096
                        or min(expiry, claim['lease_expires_at']) <= timestamp
                        or encode_json(verified['control_receipt_inspection']) != encode_json(claim)
                        or not any(tuple(p) == (claim['run_id'], 'kernel:inspect_control') for p in verified['permissions'])):
                    raise ValueError('invalid proof')
                return principal, expiry
            except Exception:
                raise StorageIsolationError('host did not authorize control receipt inspection') from None
        with self._transaction() as (connection, timestamp):
            proof = verify(timestamp)
            store = connection.execute('SELECT store_id FROM kernel_store_identity WHERE singleton=1').fetchone()
            if store is None or store[0] != claim['kernel_store_id']:
                raise CASConflictError('control receipt participant differs')
            table = 'kernel_activation_receipts' if claim['phase'] == 'activation' else 'kernel_resume_receipts'
            row = connection.execute(f'SELECT receipt_json FROM {table} WHERE operation_id=? AND run_id=?',
                                     (claim['operation_id'], claim['run_id'])).fetchone()
            receipt = None if row is None else json.loads(row[0])
            if receipt is not None:
                d = receipt.get('decision', {})
                if (any(d.get(k) != claim[k] for k in ('operation_id', 'run_id', 'kernel_store_id', 'orchestrator_store_id', 'orchestrator_incarnation'))
                        or len(encode_json(receipt).encode()) > 1048576):
                    raise CASConflictError('control receipt scope differs')
            now = self._advance_clock(connection)
            if verify(now) != proof or min(proof[1], claim['lease_expires_at']) <= self._advance_clock(connection):
                raise StorageIsolationError('control receipt inspection authority expired')
            return receipt

    def inspect_control_takeover(self, credential, *, expected_inspection):
        """Inspect an exact historical intent under a presently held host lease.

        None means absence in this Kernel transaction while the host excludes
        the old holder. A returned receipt is a fact, not current authority.
        """
        fields = {'original_takeover', 'current_lease_id', 'current_lease_fence',
                  'current_lease_expires_at', 'lease_held', 'old_holder_excluded'}
        try:
            inspection = json.loads(encode_json(expected_inspection))
            if (type(inspection) is not dict or set(inspection) != fields
                    or len(encode_json(inspection).encode()) > 1048576
                    or type(inspection['original_takeover']) is not dict
                    or type(inspection['current_lease_id']) is not str
                    or not inspection['current_lease_id'].strip()
                    or len(inspection['current_lease_id'].encode()) > 4096
                    or type(inspection['current_lease_fence']) is not int
                    or not 0 <= inspection['current_lease_fence'] < (1 << 63)
                    or inspection['lease_held'] is not True
                    or inspection['old_holder_excluded'] is not True):
                raise ValueError('invalid inspection')
            self._number(inspection['current_lease_expires_at'], 'lease expiry', minimum=0.0)
            original = inspection['original_takeover']
            if (set(original) != _TAKEOVER_FIELDS or original['phase'] not in ('activation', 'resume')
                    or type(original['original_decision']) is not dict
                    or any(original['original_decision'].get(key) != original[key] for key in
                           ('operation_id', 'run_id', 'kernel_store_id', 'orchestrator_store_id',
                            'orchestrator_incarnation', 'generation'))):
                raise ValueError('invalid original intent')
            for key in ('takeover_id', 'operation_id', 'run_id', 'kernel_store_id',
                        'orchestrator_store_id', 'orchestrator_incarnation', 'new_lease_id'):
                if type(original[key]) is not str or not original[key].strip() or len(original[key].encode()) > 4096:
                    raise ValueError('invalid original identity')
            if (type(original['new_fence']) is not int or not 0 <= original['new_fence'] < (1 << 63)
                    or inspection['current_lease_fence'] < original['new_fence']
                    or (inspection['current_lease_fence'] == original['new_fence']
                        and inspection['current_lease_id'] != original['new_lease_id'])):
                raise ValueError('stale inspection lease')
        except Exception:
            raise ValueError('invalid control takeover inspection') from None

        def verify(timestamp):
            try:
                verified = self._authority_verifier(credential)
                principal = verified['principal']
                expiry = self._number(verified['expires_at'], 'authority expiry', minimum=0.0)
                if (type(principal) is not str or not principal.strip() or len(principal.encode()) > 4096
                        or min(expiry, inspection['current_lease_expires_at']) <= timestamp
                        or encode_json(verified['control_takeover_inspection']) != encode_json(inspection)
                        or not any(tuple(p) == (original['run_id'], 'kernel:inspect_control') for p in verified['permissions'])):
                    raise ValueError('inspection authority differs')
                return principal, expiry
            except Exception:
                raise StorageIsolationError('host did not authorize takeover inspection') from None

        with self._transaction() as (connection, timestamp):
            proof = verify(timestamp)
            identity = connection.execute('SELECT store_id FROM kernel_store_identity WHERE singleton=1').fetchone()
            if identity is None or identity[0] != original['kernel_store_id']:
                raise CASConflictError('takeover inspection participant differs')
            row = connection.execute('SELECT claim_json,receipt_json FROM kernel_control_takeovers WHERE takeover_id=?',
                                     (original['takeover_id'],)).fetchone()
            if row is None:
                receipt = None
            else:
                recorded = json.loads(row[0])
                if ({k: v for k, v in recorded.items() if k != 'lease_expires_at'} !=
                        {k: v for k, v in original.items() if k != 'lease_expires_at'}):
                    raise CASConflictError('takeover inspection intent differs')
                receipt = json.loads(row[1])
            now = self._advance_clock(connection)
            if verify(now) != proof or min(proof[1], inspection['current_lease_expires_at']) <= self._advance_clock(connection):
                raise StorageIsolationError('takeover inspection authority expired')
            return receipt
