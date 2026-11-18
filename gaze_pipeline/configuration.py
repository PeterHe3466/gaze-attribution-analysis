from copy import deepcopy
import json
import math
from pathlib import Path

from .common import require


def without_descriptions(value):
    """Keep JSON valid while allowing explanations adjacent to every setting."""
    if isinstance(value, dict):
        return {key: without_descriptions(item) for key, item in value.items() if not key.startswith('_description')}
    if isinstance(value, list):
        return [without_descriptions(item) for item in value]
    return value


def load_config(path, project_root, supported_analyses=None, *, paths):
    requested = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    config = without_descriptions(requested)
    require(config.get('schema_version') == 1, 'Unsupported configuration schema_version')
    require(set(config) == {'schema_version', 'selection', 'analyses', 'rules'}, 'Unknown or missing config setting; edit input/output paths in main.py')
    require(set(paths) == {'data_root', 'order_file', 'output_root'}, 'Unknown or missing main.py path setting')
    analyses = config['analyses']
    require(bool(analyses) and len(analyses) == len(set(analyses)), 'Select at least one analysis without duplicates')
    allowed = supported_analyses if supported_analyses is not None else {'looking_time', 'spatial_roi', 'proportions'}
    require(set(analyses) <= set(allowed), 'Unknown analysis name')
    r = config['rules']
    expected = {'validation_start_ms', 'validation_end_ms', 'validation_threshold', 'measurement_start_ms',
                'measurement_end_ms', 'minimum_segment_ms', 'terminate_nonlooking_ms', 'first_look_grace_ms',
                'missing_gap_max_frames', 'screen_roi', 'track_rois', 'test_pairs', 'condition_labels',
                'proportion_denominators'}
    require(set(r) == expected, f'Unknown/missing rule keys: {set(r) ^ expected}')
    for name in expected - {'screen_roi', 'track_rois', 'test_pairs', 'condition_labels', 'proportion_denominators', 'measurement_end_ms'}:
        require(type(r[name]) in (int, float) and math.isfinite(r[name]), f'{name} must be a finite number')
    require(0 <= r['validation_start_ms'] < r['validation_end_ms'], 'Invalid validation window')
    require(0 <= r['validation_threshold'] <= 1, 'validation_threshold must be between 0 and 1')
    require(r['measurement_start_ms'] >= 0, 'measurement_start_ms must be nonnegative')
    end = r['measurement_end_ms']
    require(end is None or (type(end) in (int, float) and math.isfinite(end) and end > r['measurement_start_ms']), 'Invalid measurement_end_ms')
    for key in ['minimum_segment_ms', 'terminate_nonlooking_ms', 'first_look_grace_ms']:
        require(r[key] > 0, f'{key} must be positive')
    require(r['missing_gap_max_frames'] in [0, 1, 2], 'Supported missing_gap_max_frames: 0, 1, 2')
    require(r['test_pairs'] == [[1, 2], [3, 4]], 'This version supports Test1-2 and Test3-4 only')
    require(set(r['track_rois']) == {'left', 'right'}, 'Both left and right track ROIs are required')
    for name, roi in [('screen', r['screen_roi']), *r['track_rois'].items()]:
        for axis in ['x', 'y']:
            lo, hi = roi[f'{axis}_min'], roi[f'{axis}_max']
            require(type(lo) in (int, float) and type(hi) in (int, float) and 0 <= lo < hi <= 1, f'Invalid {name} {axis} bounds')
    left, right = r['track_rois']['left'], r['track_rois']['right']
    require(left['x_max'] <= right['x_min'], 'Track ROIs must not overlap')
    require(type(left.get('x_max_inclusive')) is bool and type(right.get('x_max_inclusive')) is bool, 'Specify track x_max_inclusive as boolean')
    require(left['x_max'] != right['x_min'] or not left['x_max_inclusive'], 'Shared edge belongs to the right ROI')
    require(bool(r['condition_labels']) and len(set(r['condition_labels'].values())) == len(r['condition_labels']), 'Condition labels must be unique')
    denominators = r['proportion_denominators']
    require(bool(denominators) and len(denominators) == len(set(denominators)) and set(denominators) <= {'roi_total', 'screen_total'}, 'Invalid proportion denominator selection')
    selection = config['selection']
    require(set(selection) == {'ages_months', 'participants'}, 'Unknown selection setting')
    require(bool(selection['ages_months']) and all(type(a) is int and a > 0 for a in selection['ages_months']), 'Select positive integer ages')
    require(isinstance(selection['participants'], list) and all(isinstance(p, str) for p in selection['participants']), 'participants must be a list of IDs')
    resolved = deepcopy(config)
    resolved['paths'] = {key: str((Path(project_root) / value).resolve()) for key, value in paths.items()}
    data = Path(resolved['paths']['data_root'])
    out = Path(resolved['paths']['output_root'])
    require(out != data and not out.is_relative_to(data), 'Output directory must be outside input data')
    require(not data.is_relative_to(out), 'Output directory must not contain input data')
    return requested, resolved
