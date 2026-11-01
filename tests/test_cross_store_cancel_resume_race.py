from test_orchestrator_control_takeover import TakeoverTests
from dispatcher_sdk.orchestrator import RevisionConflict


class CancelResumeRaceTests(TakeoverTests):
    def test_cancel_intent_after_kernel_resume_blocks_local_reopen(self):
        self.prepare_activation()
        self.takeover()
        self.sdk.activate_cross_store_revision(
            'decision', operation_id='activation', credential='operator',
            lease_credential='lease', activation_credential='activation')
        with self.sdk._transaction() as c:
            policy = '{"policy_id":"budget"}'
            c.execute("INSERT INTO sdk_revision_budget_policies VALUES('decision',?,?)", (policy, policy))
        self.kernel.inspect_budget_policy = lambda run_id, generation: {'policy_id': 'budget'}
        self.kernel.get_run_control = lambda _: {'state': self.kernel.state, 'control_epoch': self.kernel.epoch,
            'generation': self.kernel.generation, 'max_claims': 1, 'claims_used': 0, 'deadline_at': 9999999999}
        def resume(credential, worker_credential, expected_decision):
            self.kernel.state, self.kernel.epoch = 'active', 5
            return {'kind': 'revision_resume', 'decision': expected_decision}
        def fence(operation_id, run_id, expected_epoch, generation):
            raise RuntimeError('Kernel fence delayed')
        self.kernel.resume_revision = resume
        self.kernel.fence_cancelled_run = fence
        self.sdk.control_authorizer.verifier = lambda _: {'principal': 'operator',
            'permissions': [('run', 'resume'), ('run', 'cancel')]}
        self.lease.update(operation_id='resume', lease_id='resume-lease', lease_fence=3)
        def interleave(stage):
            if stage == 'after_kernel_revision_resume':
                self.lease.update(operation_id='cancel', lease_id='resume-lease', lease_fence=3)
                with self.assertRaisesRegex(RuntimeError, 'Kernel fence delayed'):
                    self.sdk.fence_cross_store_cancellation('run', operation_id='cancel',
                        credential='operator', lease_credential='lease')
                self.lease.update(operation_id='resume', lease_id='resume-lease', lease_fence=3)
        self.sdk._failpoint = interleave
        with self.assertRaises(RevisionConflict):
            self.sdk.resume_cross_store_revision('activation', operation_id='resume', credential='operator',
                lease_credential='lease', resume_credential='resume', worker_credential='worker')
        self.sdk._failpoint = lambda _: None
        self.assertEqual((self.kernel.state, self.kernel.epoch), ('active', 5))
        self.assertEqual((self.sdk.get_managed_control('run')['control_state'],
                          self.sdk.get_managed_control('run')['control_epoch']), ('paused', 4))
        with self.assertRaises(RevisionConflict):
            self.sdk.resume_cross_store_revision('activation', operation_id='resume', credential='operator',
                lease_credential='lease', resume_credential='resume', worker_credential='worker')
