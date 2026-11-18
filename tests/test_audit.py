from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from gaze_pipeline.audit import termination_table, write_audit
from gaze_pipeline.configuration import load_config
from main import publish_primary_files

ROOT = Path(__file__).resolve().parents[1]
PATHS = dict(data_root=ROOT.parent/'data_pre', order_file=ROOT.parent/'data_pre/Gaze-Order.xlsx', output_root=ROOT.parent/'Analysis output')
_, CONFIG = load_config(ROOT/'config.json', ROOT, paths=PATHS)


def trial(number, **overrides):
    row = dict(participant_id='8mo_SYNTHETIC', age_months=8, participant='SYNTHETIC', condition='Con',
               trial=f'Test{number}', pair_number=(number+1)//2, event='New' if number % 2 else 'Old',
               source='synthetic.csv', validation_pass=True, total_status='valid', first_status='valid',
               stop_reason='recording_end', trial_end_ms=18000., analysis_end_ms=18000.,
               first_pair_retained=number <= 2, total_pair_retained=number <= 2)
    return {**row, **overrides}


class AuditTests(unittest.TestCase):
    def test_early_is_review_only_and_delay_uses_rule_trigger(self):
        table = pd.DataFrame([
            trial(1, stop_reason='two_second_offscreen', analysis_end_ms=15000.),
            trial(2),
            trial(3, stop_reason='two_second_offscreen', analysis_end_ms=18000.),
            trial(4, stop_reason='measurement_end', analysis_end_ms=16000.)])
        audit = termination_table(table, CONFIG['rules'])
        self.assertEqual(audit.status.tolist(), ['delayed_termination', 'possible_early_termination_review',
                                                'rule_reached_at_recording_end', 'not_assessed_measurement_cap'])
        self.assertEqual(audit.iloc[0].delay_s, 3.)
        self.assertEqual(audit.iloc[0].rule_stop_s, 15.)
        self.assertTrue(audit.iloc[1].total_used)
        self.assertTrue(np.isnan(audit.iloc[1].delay_s))

    def test_missing_and_excluded_counts_are_separate(self):
        table = pd.DataFrame([
            trial(1, stop_reason='two_second_offscreen', analysis_end_ms=15000.), trial(2),
            trial(3, source=None, validation_pass=False, total_status='missing_trial', first_status='missing_trial'),
            trial(4, validation_pass=False, total_status='validation_failed', first_status='validation_failed')])
        people = pd.DataFrame([dict(participant_id='8mo_SYNTHETIC', age_months=8, group='8mo_CON',
                                     first_pairs_retained=1, total_pairs_retained=1)])
        record = dict(run_id='synthetic_run', started_utc='2026-11-18T00:00:00Z', git=dict(commit='test', dirty=False),
                      executed_analyses=['looking_time'])
        test_root = ROOT/'.test-tmp'
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            self.assertTrue(Path(temporary).resolve().is_relative_to(test_root.resolve()))
            ratios = {'roi_total': pd.DataFrame([dict(participant_id='8mo_SYNTHETIC', proportion_valid_pair_count=0)])}
            summary = write_audit(table, people, ratios, CONFIG, record, {}, Path(temporary))
            self.assertEqual(summary['trials']['missing'], 1)
            self.assertEqual(summary['trials']['total_present_but_excluded'], 1)
            self.assertEqual(summary['participants']['excluded_total'], 0)
            self.assertEqual(summary['termination']['possible_early_trials'], 1)
            self.assertEqual(summary['termination']['delayed_trials'], 1)
            self.assertEqual(summary['proportions']['roi_total']['participants_excluded'], 1)
            self.assertEqual(summary['proportion_pair_reductions'][0]['participant_id'], '8mo_SYNTHETIC')
            self.assertIn('Possible early termination', (Path(temporary)/'audit.md').read_text(encoding='utf-8'))

    def test_only_two_primary_files_are_published_and_snapshot_is_retained(self):
        test_root = ROOT/'.test-tmp'
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            root = Path(temporary)
            self.assertTrue(root.resolve().is_relative_to(test_root.resolve()))
            snapshot = root/'details'/'synthetic_run'
            snapshot.mkdir(parents=True)
            for name in ['analysis_ready.csv', 'audit.md', 'termination_trials.csv']:
                (snapshot/name).write_text('new run', encoding='utf-8')
            (root/'analysis_ready.csv').write_text('previous run', encoding='utf-8')
            publish_primary_files(snapshot, root)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['analysis_ready.csv', 'audit.md', 'details'])
            self.assertEqual((root/'analysis_ready.csv').read_text(), 'new run')
            self.assertTrue((snapshot/'analysis_ready.csv').is_file())
            self.assertFalse((root/'termination_trials.csv').exists())


if __name__ == '__main__':
    unittest.main()
