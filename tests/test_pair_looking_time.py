"""Pair exports must preserve the established trial timing and eligibility rules."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from gaze_pipeline.configuration import load_config, without_descriptions
from gaze_pipeline.pair_looking_time import calculate_pair_looking_time, extract_pair_looking_time
from gaze_pipeline.verification import verify_pair_results
from main import SUPPORTED_ANALYSES

ROOT = Path(__file__).resolve().parents[1]
RULES = without_descriptions(json.loads((ROOT / 'config.json').read_text(encoding='utf-8')))['rules']


def example(first_flags=(True, True), total_flags=(True, True)):
    person = dict(participant_id='8mo_SYNTHETIC', age_months=8, participant='SYNTHETIC',
                  condition='CON', group='8mo_CON', order_number=1, test_sequence='ONON')
    # Deliberately use Old-before-New and shuffled rows to avoid positional matching.
    rows = [
        dict(pair_number=1, event='Old', first_s=2., total_s=6.),
        dict(pair_number=1, event='New', first_s=4., total_s=10.),
        dict(pair_number=2, event='Old', first_s=4., total_s=14.),
        dict(pair_number=2, event='New', first_s=8., total_s=18.),
    ]
    for row in rows:
        row['participant_id'] = person['participant_id']
        for metric, flags in [('first', first_flags), ('total', total_flags)]:
            kept = flags[row['pair_number'] - 1]
            row[f'{metric}_pair_retained'] = kept
            row[f'{metric}_pair_reason'] = ('retained' if kept else
                                           'first_pair_incomplete' if not flags[0] else 'second_pair_incomplete')
    for metric, flags in [('first', first_flags), ('total', total_flags)]:
        person[f'{metric}_pairs_retained'] = sum(flags)
        for event in ['New', 'Old']:
            values = [r[f'{metric}_s'] for r in rows if r['event'] == event and flags[r['pair_number'] - 1]]
            person[f'{event.lower()}_{metric}_s'] = float(np.mean(values)) if values else np.nan
    return pd.DataFrame(rows).iloc[[3, 0, 2, 1]].reset_index(drop=True), pd.DataFrame([person])


class PairLookingTimeTests(unittest.TestCase):
    def test_separate_values_use_pair_and_event_not_row_order(self):
        trials, people = example()
        wide, pairs = calculate_pair_looking_time(trials, people, RULES)
        row = wide.iloc[0]
        expected = {'pair1_new_first_s': 4., 'pair1_old_first_s': 2.,
                    'pair2_new_first_s': 8., 'pair2_old_first_s': 4.,
                    'pair1_new_total_s': 10., 'pair1_old_total_s': 6.,
                    'pair2_new_total_s': 18., 'pair2_old_total_s': 14.}
        for column, value in expected.items():
            self.assertEqual(row[column], value)
        self.assertAlmostEqual(row.pair2_log10_total_new, np.log10(18.))
        self.assertEqual(pairs.pair_number.tolist(), [1, 2])
        self.assertEqual(pairs.new_total_s.tolist(), [10., 18.])
        self.assertTrue(verify_pair_results(trials, people, wide)['passed'])

    def test_first_and_total_pairs_have_independent_eligibility(self):
        trials, people = example(first_flags=(True, False))
        wide, pairs = calculate_pair_looking_time(trials, people, RULES)
        row = wide.iloc[0]
        self.assertEqual(row.pair2_first_retained, 0)
        self.assertEqual(row.pair2_total_retained, 1)
        self.assertTrue(np.isnan(row.pair2_new_first_s))
        self.assertTrue(np.isnan(row.pair2_log10_first_old))
        self.assertEqual(row.pair2_new_total_s, 18.)
        self.assertEqual(pairs.iloc[1].first_pair_reason, 'second_pair_incomplete')
        self.assertTrue(verify_pair_results(trials, people, wide)['passed'])

    def test_invalid_first_pair_masks_both_pairs_without_zero_filling(self):
        trials, people = example(first_flags=(False, False), total_flags=(False, False))
        trials.loc[trials.pair_number.eq(1) & trials.event.eq('New'), ['first_s', 'total_s']] = np.nan
        wide, pairs = calculate_pair_looking_time(trials, people, RULES)
        outcomes = [c for c in wide if c.endswith('_s') or '_log10_' in c]
        self.assertTrue(wide[outcomes].isna().all().all())
        self.assertEqual(wide.filter(regex='_retained$').to_numpy().sum(), 0)
        self.assertEqual(pairs.iloc[1].total_pair_reason, 'first_pair_incomplete')
        self.assertTrue(verify_pair_results(trials, people, wide)['passed'])

    def test_malformed_pair_inputs_are_rejected(self):
        trials, people = example(first_flags=(False, True))
        with self.assertRaisesRegex(ValueError, 'cannot be retained'):
            calculate_pair_looking_time(trials, people, RULES)
        trials, people = example()
        trials.loc[trials.pair_number.eq(1), 'event'] = 'New'
        with self.assertRaisesRegex(ValueError, 'exactly one New and one Old'):
            calculate_pair_looking_time(trials, people, RULES)
        trials, people = example()
        trials.loc[0, 'total_pair_retained'] = False
        with self.assertRaisesRegex(ValueError, 'retention flags'):
            calculate_pair_looking_time(trials, people, RULES)

    def test_verification_rejects_changed_pair_duration(self):
        trials, people = example()
        wide, _ = calculate_pair_looking_time(trials, people, RULES)
        wide.loc[0, 'pair1_new_total_s'] = 11.
        with self.assertRaisesRegex(ValueError, 'differs from trial duration'):
            verify_pair_results(trials, people, wide)

    def test_pair_csvs_preserve_rows_and_missing_values(self):
        trials, people = example(total_flags=(True, False))
        test_root = ROOT / '.test-tmp'
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            output = Path(temporary)
            exported = extract_pair_looking_time(trials, people, RULES, output)
            wide = pd.read_csv(output / 'pair_looking_time_participants.csv')
            pairs = pd.read_csv(output / 'pair_looking_time_pairs.csv')
            self.assertEqual(len(wide), 1)
            self.assertEqual(len(pairs), 2)
            self.assertTrue(np.isnan(wide.iloc[0].pair2_old_total_s))
            self.assertEqual(pairs.iloc[1].new_first_s, 8.)
            pd.testing.assert_frame_equal(wide, exported, check_dtype=False, atol=1e-9, rtol=0)

    def test_deferred_analyses_cannot_be_selected_in_main(self):
        original = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        paths = dict(data_root=ROOT.parent / 'data_pre',
                     order_file=ROOT.parent / 'data_pre/Gaze-Order.xlsx',
                     output_root=ROOT.parent / 'Analysis output')
        test_root = ROOT / '.test-tmp'
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            config_path = Path(temporary) / 'deferred.json'
            for analysis in ['spatial_roi', 'proportions']:
                with self.subTest(analysis=analysis):
                    requested = deepcopy(original)
                    requested['analyses'] = [analysis]
                    config_path.write_text(json.dumps(requested), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'Unknown analysis name'):
                        load_config(config_path, ROOT, SUPPORTED_ANALYSES, paths=paths)


if __name__ == '__main__':
    unittest.main()
