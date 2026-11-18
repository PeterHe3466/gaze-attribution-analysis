import gzip

import numpy as np
import pandas as pd

from .common import require, log10_positive, write_csv
from .inputs import read_trial
from .quality import clean_pupil_artifacts


def classify(x, y, valid, rois):
    code = np.zeros(len(x), dtype=np.int8)
    finite = np.isfinite(x) & np.isfinite(y) & valid
    for label, number in [('left', 1), ('right', 2)]:
        roi = rois[label]
        upper = x <= roi['x_max'] if roi['x_max_inclusive'] else x < roi['x_max']
        inside = finite & (x >= roi['x_min']) & upper & (y >= roi['y_min']) & (y <= roi['y_max'])
        require(not (inside & (code != 0)).any(), 'A sample belongs to both track ROIs')
        code[inside] = number
    return code


def interval_weights(times, segments, stop, start):
    if len(times) == 0:
        return np.array([], dtype=float)
    next_times = np.r_[times[1:], times[-1]]
    weights = np.zeros(len(times), dtype=float)
    for lo, hi in segments:
        weights += np.maximum(0, np.minimum(next_times, min(hi, stop)) - np.maximum(times, max(lo, start)))
    require((weights >= 0).all() and (weights <= np.maximum(0, next_times-times) + 1e-8).all(), 'Overlapping or invalid accepted segments')
    return weights


def extract_spatial(trials, people, metadata, rules, output):
    rows, segment_rows = [], []
    with gzip.open(output / 'frame_roi_assignments.csv.gz', 'wt', encoding='utf-8', newline='') as frame_file:
        first_frame = True
        for tr in trials.itertuples():
            condition = rules['condition_labels'][tr.condition]
            oldside, event = tr.side, tr.event
            require(oldside in ['Left', 'Right'] and event in ['New', 'Old'], 'Unexpected stimulus side/event')
            newside = 'Right' if oldside == 'Left' else 'Left'
            row = dict(participant_id=tr.participant_id, age_months=tr.age_months, condition=condition,
                       group=f'{tr.age_months}mo_{condition}', trial=tr.trial, pair_number=tr.pair_number,
                       event=event, stimulus_file=tr.expected_stimulus, source=tr.source,
                       old_location_side=oldside, new_location_side=newside, validation_pass=bool(tr.validation_pass),
                       validation_ratio=tr.validation_ratio, pair_retained=bool(tr.total_pair_retained),
                       status=tr.total_status, window_start_s=rules['measurement_start_ms']/1000,
                       analysis_end_s=tr.analysis_end_ms/1000, stop_reason=tr.stop_reason,
                       whole_screen_total_s=tr.total_s, left_track_s=np.nan, right_track_s=np.nan,
                       new_location_s=np.nan, old_location_s=np.nan, other_screen_s=np.nan, unassigned_accepted_s=np.nan)
            if pd.notna(tr.source) and tr.validation_pass:
                data = read_trial(tr.source, int(tr.participant[1:]), tr.expected_stimulus, tr.trial)
                info = metadata[(tr.participant_id, tr.trial)]
                end = rules['measurement_end_ms']
                measurement = data[data.frame_time.ge(rules['measurement_start_ms']) & (data.frame_time.le(end) if end is not None else True)]
                m, _ = clean_pupil_artifacts(measurement, rules)
                times = m.frame_time.to_numpy(dtype=float)
                x, y = m.filtered_gaze_pos_x.to_numpy(dtype=float), m.filtered_gaze_pos_y.to_numpy(dtype=float)
                valid = m.is_looking.to_numpy(dtype=bool)
                weights = interval_weights(times, info['segments'], info['stop'], rules['measurement_start_ms'])
                require(np.isclose(weights.sum(), tr.raw_total_ms, atol=1e-8, rtol=0), 'Spatial intervals do not sum to whole-screen looking')
                code = classify(x, y, valid, rules['track_rois'])
                left, right = weights[code == 1].sum()/1000, weights[code == 2].sum()/1000
                other = weights[(code == 0) & valid & np.isfinite(x) & np.isfinite(y)].sum()/1000
                unknown = weights[(code == 0) & ~(valid & np.isfinite(x) & np.isfinite(y))].sum()/1000
                # Validation-passing, nonpositive whole-screen trials remain excluded from aggregation.
                require(np.isclose(left+right+other+unknown, tr.raw_total_ms/1000, atol=1e-9, rtol=0), 'Spatial time partition mismatch')
                row.update(left_track_s=float(left), right_track_s=float(right), other_screen_s=float(other), unassigned_accepted_s=float(unknown),
                           new_location_s=float(right if newside == 'Right' else left), old_location_s=float(left if oldside == 'Left' else right))
                for lo, hi in info['segments']:
                    segment_rows.append(dict(participant_id=tr.participant_id, trial=tr.trial, start_s=lo/1000, end_s=hi/1000, duration_s=(hi-lo)/1000))
                use = times <= info['stop']
                audit = pd.DataFrame(dict(participant_id=tr.participant_id, trial=tr.trial, frame_no=m.frame_no.to_numpy()[use],
                                          frame_time_ms=times[use], x=x[use], y=y[use], screen_looking=valid[use],
                                          roi_code=code[use], accepted_overlap_ms=weights[use]))
                audit.to_csv(frame_file, index=False, header=first_frame, float_format='%.8f')
                first_frame = False
            rows.append(row)
    trialout = pd.DataFrame(rows)
    wide = []
    for person in people.to_dict('records'):
        kept = trialout[trialout.participant_id.eq(person['participant_id']) & trialout.pair_retained]
        pairs = sorted(kept.pair_number.unique())
        require(pairs == list(range(1, person['valid_pair_count']+1)), 'Spatial pair prefix mismatch')
        row = {key: person[key] for key in ['participant_id', 'age_months', 'condition', 'group', 'order_number', 'test_sequence', 'valid_pair_count', 'pair1_valid', 'pair2_valid']}
        for label, pairset in [('pair1', [1]), ('pair2', [2]), ('totalpairs', pairs)]:
            selected = kept[kept.pair_number.isin(pairset)]
            for event in ['New', 'Old']:
                values = selected[selected.event.eq(event)]
                for loc in ['new', 'old']:
                    value = float(values[f'{loc}_location_s'].mean()) if len(values) else np.nan
                    row[f'{label}_event{event}_{loc}loc_s'] = value
                    row[f'{label}_event{event}_{loc}loc_log10'] = log10_positive(value)
        wide.append(row)
    participants = pd.DataFrame(wide)
    write_csv(trialout, output / 'spatial_roi_trials.csv')
    write_csv(participants, output / 'spatial_roi_participants.csv')
    write_csv(pd.DataFrame(segment_rows, columns=['participant_id', 'trial', 'start_s', 'end_s', 'duration_s']), output / 'accepted_screen_looking_segments.csv')
    return trialout, participants
