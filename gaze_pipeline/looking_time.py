import numpy as np
import pandas as pd

from .common import require, retained_prefix, log10_positive, write_csv
from .inputs import read_trial
from .quality import clean_pupil_artifacts
from .timing import process_totalLT, process_firstLook


def extract_looking_time(inventory, rules, output):
    rows, metadata = [], {}
    with (output / 'total_looking_segments.log').open('w', encoding='utf-8') as total_log, \
         (output / 'first_looking_segments.log').open('w', encoding='utf-8') as first_log:
        for item in inventory.to_dict('records'):
            row = {**item, 'validation_pass': False, 'validation_ratio': np.nan,
                   'validation_frames': 0, 'validation_looking_frames': np.nan,
                   'first_s': np.nan, 'total_s': np.nan, 'raw_first_ms': np.nan, 'raw_total_ms': np.nan,
                   'first_status': 'missing_trial', 'total_status': 'missing_trial',
                   'trial_end_ms': np.nan, 'measurement_first_frame_ms': np.nan,
                   'analysis_end_ms': np.nan, 'stop_reason': 'missing_trial',
                   'first_late_termination_ms': np.nan, 'total_late_termination_ms': np.nan}
            if pd.notna(item['source']):
                data = read_trial(item['source'], int(item['participant'][1:]), item['expected_stimulus'], item['trial'])
                stats_t, stats_f = [], []
                total = process_totalLT(data, item['participant_id'], item['trial'], stats_t, total_log, rules)
                first = process_firstLook(data, item['participant_id'], item['trial'], stats_f, first_log, rules)
                require(stats_t[0]['passed'] == stats_f[0]['passed'], 'First/total validation mismatch')
                require(not (np.isfinite(first) and first > 0) or (np.isfinite(total) and first <= total + 1e-9), 'First look exceeds total looking')
                end = rules['measurement_end_ms']
                measurement = data[data.frame_time.ge(rules['measurement_start_ms']) & (data.frame_time.le(end) if end is not None else True)]
                validation, fixed = clean_pupil_artifacts(data[data.frame_time.between(rules['validation_start_ms'], rules['validation_end_ms'])], rules)
                passed = bool(stats_t[0]['passed'])
                for metric, value in [('first', first), ('total', total)]:
                    positive = np.isfinite(value) and value > 0
                    row[f'raw_{metric}_ms'] = value
                    row[f'{metric}_s'] = value / 1000 if positive else np.nan
                    row[f'{metric}_status'] = ('validation_failed' if not passed else 'no_measurement_frames' if measurement.empty
                                               else 'nonpositive_duration' if not positive else 'valid')
                stop = stats_t[0]['termination_time_ms']
                observed_end = float(measurement.frame_time.iloc[-1]) if len(measurement) else np.nan
                segments = stats_t[0]['accepted_segments_ms']
                if passed:
                    require(np.isclose(sum(hi-lo for lo, hi in segments), total, atol=1e-9, rtol=0), 'Structured segments do not sum to total')
                metadata[(item['participant_id'], item['trial'])] = dict(segments=segments, stop=stop if stop is not None else observed_end)
                row.update(validation_pass=passed, validation_ratio=float(stats_t[0]['valid_proportion']),
                           validation_frames=len(validation), validation_looking_frames=int(validation.is_looking.sum()),
                           validation_artifacts_filled=fixed, trial_end_ms=float(data.frame_time.iloc[-1]),
                           measurement_first_frame_ms=float(measurement.frame_time.iloc[0]) if len(measurement) else np.nan,
                           analysis_end_ms=(stop if stop is not None else observed_end) if passed else np.nan,
                           stop_reason='validation_failed' if not passed else 'two_second_offscreen' if stop is not None else 'no_measurement_frames' if measurement.empty else 'measurement_end' if end is not None and data.frame_time.iloc[-1] > end else 'recording_end',
                           total_late_termination_ms=stats_t[0]['late_termination_ms'],
                           first_late_termination_ms=stats_f[0]['late_termination_ms'])
            rows.append(row)
    trials = pd.DataFrame(rows)
    summaries = []
    pair_numbers = list(range(1, len(rules['test_pairs'])+1))
    for ident, block in trials.groupby('participant_id', sort=False):
        person = {key: block.iloc[0][key] for key in ['participant_id', 'age_months', 'participant', 'condition', 'order_number', 'test_sequence']}
        person['condition'] = rules['condition_labels'][person['condition']]
        person['group'] = f"{person['age_months']}mo_{person['condition']}"
        for metric in ['first', 'total']:
            complete = [int(pair) for pair, b in block.groupby('pair_number') if len(b) == 2 and set(b.event) == {'New', 'Old'} and b[f'{metric}_s'].gt(0).all()]
            kept = retained_prefix(complete, pair_numbers)
            person[f'{metric}_pairs_retained'] = len(kept)
            for idx, tr in block.iterrows():
                trials.loc[idx, f'{metric}_pair_retained'] = int(tr.pair_number) in kept
                trials.loc[idx, f'{metric}_pair_reason'] = 'retained' if int(tr.pair_number) in kept else 'first_pair_incomplete' if 1 not in complete else 'second_pair_incomplete'
            for event in ['New', 'Old']:
                values = block.loc[block.pair_number.isin(kept) & block.event.eq(event), f'{metric}_s']
                person[f'{event.lower()}_{metric}_s'] = float(values.mean()) if len(values) else np.nan
                person[f'log10_{metric}_{event.lower()}'] = log10_positive(person[f'{event.lower()}_{metric}_s'])
        # Never silently drop participants or conflate metric-specific pair sets.
        person['valid_pair_count'] = person['total_pairs_retained']
        for pair in pair_numbers:
            retained = block.index[block.pair_number.eq(pair)]
            person[f'pair{pair}_valid'] = int(trials.loc[retained, 'total_pair_retained'].all())
        summaries.append(person)
    participants = pd.DataFrame(summaries)
    for column in ['first_pair_retained', 'total_pair_retained']:
        trials[column] = trials[column].astype(bool)
    write_csv(trials, output / 'looking_time_trials.csv')
    write_csv(participants, output / 'looking_time_participants.csv')
    return trials, participants, metadata
