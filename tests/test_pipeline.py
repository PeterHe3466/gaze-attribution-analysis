from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from gaze_pipeline.configuration import load_config, without_descriptions
from gaze_pipeline.common import retained_prefix
from gaze_pipeline.quality import clean_pupil_artifacts, check_validation_period
from gaze_pipeline.spatial_roi import classify, interval_weights
from gaze_pipeline.proportions import calculate_proportions, META
from gaze_pipeline.timing import process_totalLT, process_firstLook

ROOT = Path(__file__).resolve().parents[1]
RULES = without_descriptions(json.loads((ROOT/'config.json').read_text(encoding='utf-8')))['rules']
TEST_PATHS = dict(data_root=ROOT.parent/'data_pre', order_file=ROOT.parent/'data_pre/Gaze-Order.xlsx', output_root=ROOT.parent/'Analysis output')


def synthetic_trial(end=18000):
    times = np.arange(0, end+1, 20)
    return pd.DataFrame(dict(frame_time=times, frame_no=np.arange(len(times)),
                             **{'Screen-Space_pupil': 4.}, filtered_gaze_pos_x=.5, filtered_gaze_pos_y=.5))


class TimingTests(unittest.TestCase):
    def test_historical_timing_cases(self):
        cases = [
            ('continuous', 18000, lambda t: np.ones(len(t), bool), 5000, 5000),
            ('offscreen_2s', 20000, lambda t: (t < 15000) | (t >= 17500), 2000, 2000),
            ('short_switch_bridged', 18000, lambda t: (t < 15000) | (t >= 15200), 5000, 5000),
            ('two_looks', 18000, lambda t: (t < 15000) | (t >= 16000), 4000, 2000),
            ('initial_grace', 18000, lambda t: (t < 13000) | (t >= 14000), 4000, 4000),
            ('initial_2s_away', 18000, lambda t: (t < 13000) | (t >= 15200), 0, 0),
            ('no_measurement', 12000, lambda t: np.ones(len(t), bool), 0, 0),
            ('no_64s_cap', 74000, lambda t: np.ones(len(t), bool), 61000, 61000),
            ('no_last_frame_padding', 17980, lambda t: np.ones(len(t), bool), 4980, 4980)]
        for name, end, looking, total_expected, first_expected in cases:
            with self.subTest(name=name):
                data = synthetic_trial(end)
                data.loc[~looking(data.frame_time.to_numpy()), 'Screen-Space_pupil'] = np.nan
                stats = []
                total = process_totalLT(data, 'SYNTHETIC', name, stats, io.StringIO(), RULES)
                first = process_firstLook(data, 'SYNTHETIC', name, [], io.StringIO(), RULES)
                self.assertEqual(total, total_expected)
                self.assertEqual(first, first_expected)
                self.assertEqual(sum(hi-lo for lo, hi in stats[0]['accepted_segments_ms']), total)

    def test_validation_threshold_and_inclusive_window(self):
        data = synthetic_trial().query('7000 <= frame_time < 10000').copy()
        for n in [74, 75, 76]:
            data['Screen-Space_pupil'] = [4.]*n+[np.nan]*(150-n)
            passed, ratio = check_validation_period(data, RULES)
            self.assertEqual(passed, n >= 75)
            self.assertAlmostEqual(ratio, n/150)
        rules = deepcopy(RULES)
        rules['validation_threshold'] = .6
        self.assertFalse(check_validation_period(data, rules)[0])
        full = synthetic_trial()
        self.assertEqual(len(full[full.frame_time.between(7000, 10000)]), 151)

    def test_configuration_reaches_timing_functions(self):
        rules = deepcopy(RULES)
        rules['measurement_start_ms'], rules['measurement_end_ms'] = 14000, 16000
        total = process_totalLT(synthetic_trial(), 'SYNTHETIC', 'changed_window', [], io.StringIO(), rules)
        self.assertEqual(total, 2000)

    def test_roi_outside_is_not_a_missing_gap(self):
        for gap in [1, 2]:
            data = synthetic_trial().iloc[:gap+2].copy()
            data.loc[data.index[1:-1], 'filtered_gaze_pos_x'] = .01
            cleaned, n = clean_pupil_artifacts(data, RULES)
            self.assertEqual(cleaned.is_looking.tolist(), [True]+[False]*gap+[True])
            self.assertEqual(n, 0)
            data['filtered_gaze_pos_x'] = .5
            data.loc[data.index[1:-1], 'Screen-Space_pupil'] = np.nan
            cleaned, n = clean_pupil_artifacts(data, RULES)
            self.assertTrue(cleaned.is_looking.all())
            self.assertEqual(n, gap)

    def test_failed_validation_is_missing(self):
        data = synthetic_trial()
        data.loc[data.frame_time.between(7000, 10000), 'filtered_gaze_pos_y'] = .99
        self.assertTrue(np.isnan(process_totalLT(data, 'SYNTHETIC', 'invalid', [], io.StringIO(), RULES)))


class SpatialAndRatioTests(unittest.TestCase):
    def test_shared_edge_and_interval_accounting(self):
        x = np.array([.077, .5, .923, .076999, .923001])
        y = np.full(5, .65)
        self.assertEqual(classify(x, y, np.ones(5, dtype=bool), RULES['track_rois']).tolist(), [1, 2, 2, 0, 0])
        weights = interval_weights(np.array([13000., 13020., 13040., 13060.]), [(13010, 13050)], 13060, 13000)
        np.testing.assert_array_equal(weights, [10, 20, 10, 0])

    def test_incomplete_first_pair_cannot_use_second(self):
        self.assertEqual(retained_prefix([2], [1, 2]), [])
        self.assertEqual(retained_prefix([1], [1, 2]), [1])

    def test_zero_denominator_and_mean_of_trial_proportions(self):
        person = dict(zip(META, ['SYNTHETIC', 8, 'CON', '8mo_CON', 1, 'NONO', 2, 1, 1]))
        for pair in ['pair1', 'pair2', 'totalpairs']:
            for event in ['New', 'Old']:
                for loc in ['new', 'old']:
                    person[f'{pair}_event{event}_{loc}loc_s'] = 0.
                    person[f'{pair}_event{event}_{loc}loc_log10'] = np.nan
        people = pd.DataFrame([person])
        trials = pd.DataFrame([
            dict(participant_id='SYNTHETIC', trial='Test1', pair_number=1, event='New', new_location_s=1., old_location_s=1., whole_screen_total_s=4., pair_retained=True),
            dict(participant_id='SYNTHETIC', trial='Test2', pair_number=1, event='Old', new_location_s=1., old_location_s=3., whole_screen_total_s=5., pair_retained=True),
            dict(participant_id='SYNTHETIC', trial='Test3', pair_number=2, event='New', new_location_s=9., old_location_s=1., whole_screen_total_s=10., pair_retained=True),
            dict(participant_id='SYNTHETIC', trial='Test4', pair_number=2, event='Old', new_location_s=0., old_location_s=0., whole_screen_total_s=5., pair_retained=True)])
        roi, _, _ = calculate_proportions(trials, people, 'roi_total')
        self.assertEqual(roi.iloc[0].proportion_valid_pair_count, 1)
        self.assertEqual(roi.iloc[0].totalpairs_newgoal_ball_prop, .5)
        screen, _, _ = calculate_proportions(trials, people, 'screen_total')
        self.assertEqual(screen.iloc[0].proportion_valid_pair_count, 2)
        self.assertAlmostEqual(screen.iloc[0].totalpairs_newgoal_ball_prop, (.25+.9)/2)
        self.assertEqual(screen.iloc[0].pair2_oldgoal_ball_prop, 0.)
        self.assertTrue(np.isnan(screen.iloc[0].pair2_oldgoal_ball_prop_log10))
        trials.loc[3, ['new_location_s', 'old_location_s']] = [1., 1.]
        roi, _, _ = calculate_proportions(trials, people, 'roi_total')
        self.assertAlmostEqual(roi.iloc[0].totalpairs_newgoal_ball_prop, (.5+.9)/2)
        self.assertNotAlmostEqual(roi.iloc[0].totalpairs_newgoal_ball_prop, (1+9)/(2+10))


class ConfigurationTests(unittest.TestCase):
    def test_unknown_rule_and_overlapping_output_rejected(self):
        config = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
        test_root = ROOT/'.test-tmp'
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            self.assertTrue(Path(temporary).resolve().is_relative_to(test_root.resolve()))
            path = Path(temporary)/'invalid.json'
            config['rules']['typo_threshold'] = .5
            path.write_text(json.dumps(config), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_config(path, ROOT, paths=TEST_PATHS)
            del config['rules']['typo_threshold']
            path.write_text(json.dumps(config), encoding='utf-8')
            overlapping = {**TEST_PATHS, 'output_root': TEST_PATHS['data_root']}
            with self.assertRaises(ValueError):
                load_config(path, ROOT, paths=overlapping)

    def test_descriptions_are_not_computational_settings(self):
        raw, resolved = load_config(ROOT/'config.json', ROOT, paths=TEST_PATHS)
        self.assertIn('_description', raw)
        self.assertNotIn('_description', resolved)
        self.assertEqual(resolved['rules'], RULES)
        self.assertNotIn('paths', raw)
        self.assertEqual(resolved['paths']['output_root'], str(TEST_PATHS['output_root'].resolve()))


if __name__ == '__main__':
    unittest.main()
