"""Snapshot rehearsal must preserve source bytes and prove the existing epoch path."""
import importlib.util
from test_monitor import Temporary, NOW

spec=importlib.util.spec_from_file_location('rehearse131','operations/admin-alerts/rehearse_v1_3_1.py')
rehearsal=importlib.util.module_from_spec(spec);spec.loader.exec_module(rehearsal)


class RehearsalTests(Temporary):
    def test_synthetic_existing_epoch_projection(self):
        result=rehearsal.synthetic(NOW)
        self.assertEqual(result['would_invalidate_idle_unknown'],1)
        self.assertTrue(result['epoch_preserved'])
        self.assertTrue(result['resume_ready_after_cleanup'])
        self.assertTrue(result['resume_database_bytes_unchanged'])
        self.assertTrue(result['attempt_history_preserved'])
        self.assertEqual(result['notification_epoch'][0]['id'],'ADMIN_NOTIFICATION_EPOCH_V1')
        self.assertEqual(result['activation_review_required'],[])
        for field in ('new_epoch_rows','telegram_sends','football_api_calls','prematch_controls','live_mutations'):
            self.assertEqual(result[field],0)
