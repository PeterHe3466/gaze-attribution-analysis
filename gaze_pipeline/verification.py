from pathlib import Path

import numpy as np
import pandas as pd

from .common import require


def verify_results(looking_trials, looking_people, spatial_trials=None, spatial_people=None, proportions=None):
    proportions = {} if proportions is None else proportions
    require(looking_people.participant_id.is_unique, 'Duplicate participant results')
    require(len(looking_trials) == 4*len(looking_people), 'Expected four trial slots per participant')
    for metric in ['first', 'total']:
        retained = looking_trials[f'{metric}_pair_retained']
        require(looking_trials.loc[retained, f'{metric}_s'].gt(0).all(), 'Retained nonpositive duration')
        require(looking_trials.loc[retained, 'validation_pass'].all(), 'Retained invalid trial')
    checks = dict(participants=len(looking_people), present_test_trials=int(looking_trials.source.notna().sum()),
                  missing_test_trials=int(looking_trials.source.isna().sum()),
                  validation_failed=int(looking_trials.total_status.eq('validation_failed').sum()),
                  total_pair_counts={str(int(k)): int(v) for k, v in looking_people.valid_pair_count.value_counts().sort_index().items()},
                  group_counts={str(k): int(v) for k, v in looking_people.groupby('group').size().items()})
    if spatial_trials is not None:
        used = spatial_trials[spatial_trials.pair_retained]
        values = used[['left_track_s', 'right_track_s', 'other_screen_s', 'unassigned_accepted_s']].sum(axis=1)
        require(np.allclose(values, used.whole_screen_total_s, atol=1e-9, rtol=0), 'Spatial time accounting failed')
        require((used.left_track_s + used.right_track_s <= used.whole_screen_total_s+1e-9).all(), 'Track time exceeds screen time')
        for person in spatial_people.itertuples():
            for event in ['New', 'Old']:
                for loc in ['new', 'old']:
                    raw = [getattr(person, f'pair{p}_event{event}_{loc}loc_s') for p in [1, 2]]
                    available = np.asarray(raw)[np.isfinite(raw)]
                    require(len(available) == person.valid_pair_count, 'Spatial pair count mismatch')
                    total = getattr(person, f'totalpairs_event{event}_{loc}loc_s')
                    require((len(available) == 0 and np.isnan(total)) or np.isclose(available.mean(), total, atol=1e-9, rtol=0), 'Spatial pair mean mismatch')
        checks['spatial_accounting_passed'] = True
    for name, table in proportions.items():
        columns = [c for c in table if c.endswith('_prop')]
        values = table[columns].to_numpy(dtype=float)
        require(((values >= -1e-12) | np.isnan(values)).all() and ((values <= 1+1e-12) | np.isnan(values)).all(), 'Proportion outside [0,1]')
        checks[name+'_pair_counts'] = {str(int(k)): int(v) for k, v in table.proportion_valid_pair_count.value_counts().sort_index().items()}
    checks['result_invariants_passed'] = True
    return checks


def verify_pair_results(trials, people, pair_people):
    """Check separate pair values against trial durations and existing pair means."""
    require(pair_people.participant_id.is_unique, 'Duplicate pair-export participants')
    require(set(pair_people.participant_id) == set(people.participant_id),
            'Pair-export participants differ from looking-time participants')
    paired = pair_people.set_index('participant_id')
    for person in people.to_dict('records'):
        result = paired.loc[person['participant_id']]
        block = trials[trials.participant_id.eq(person['participant_id'])]
        for metric in ['first', 'total']:
            for event in ['New', 'Old']:
                values = []
                for number in [1, 2]:
                    trial = block[block.pair_number.eq(number) & block.event.eq(event)]
                    require(len(trial) == 1, 'Ambiguous pair/event in verification')
                    kept = bool(trial[f'{metric}_pair_retained'].iloc[0])
                    require(result[f'pair{number}_{metric}_retained'] == int(kept),
                            'Pair-export retention differs from trial retention')
                    expected = float(trial[f'{metric}_s'].iloc[0]) if kept else np.nan
                    actual = result[f'pair{number}_{event.lower()}_{metric}_s']
                    require(np.isclose(actual, expected, atol=1e-9, rtol=0, equal_nan=True),
                            'Pair-export duration differs from trial duration')
                    expected_log = np.log10(expected) if np.isfinite(expected) and expected > 0 else np.nan
                    require(np.isclose(result[f'pair{number}_log10_{metric}_{event.lower()}'],
                                       expected_log, atol=1e-9, rtol=0, equal_nan=True),
                            'Pair-export log10 differs from duration')
                    if np.isfinite(actual):
                        values.append(actual)
                average = float(np.mean(values)) if values else np.nan
                require(np.isclose(average, person[f'{event.lower()}_{metric}_s'],
                                   atol=1e-9, rtol=0, equal_nan=True),
                        'Separate pairs do not reproduce the existing looking-time mean')
    return dict(participants=len(people), pairs_per_participant=2,
                trial_values_match=True, retained_pair_means_match=True, passed=True)


def compare_table(actual, reference_path, keys, ignored=(), normalize_condition=False):
    reference = pd.read_csv(reference_path)
    actual = actual.copy()
    if normalize_condition and 'condition' in reference:
        reference['condition'] = reference.condition.replace({'Con': 'CON', 'Int': 'INC'})
    if 'participant_id' in keys:
        reference = reference[reference.participant_id.isin(actual.participant_id)]
        new_count = int((~actual.participant_id.isin(reference.participant_id)).sum())
        actual = actual[actual.participant_id.isin(reference.participant_id)]
        require(len(reference) > 0, 'No participants overlap the historical reference')
    else:
        new_count = 0
    require(not actual.duplicated(keys).any() and not reference.duplicated(keys).any(), f'Duplicate comparison keys: {reference_path.name}')
    actual = actual.set_index(keys).sort_index()
    reference = reference.set_index(keys).sort_index()
    require(actual.index.equals(reference.index), f'Reference row mismatch: {reference_path.name}')
    columns = [c for c in reference.columns if c not in ignored]
    require(set(columns) <= set(actual), f'Missing reference columns: {set(columns)-set(actual)}')
    max_error = 0.0
    numeric_cells = 0
    for column in columns:
        a, b = actual[column], reference[column]
        if pd.api.types.is_numeric_dtype(b) or pd.api.types.is_bool_dtype(b):
            av, bv = pd.to_numeric(a).to_numpy(dtype=float), pd.to_numeric(b).to_numpy(dtype=float)
            require(np.allclose(av, bv, atol=1e-9, rtol=0, equal_nan=True), f'Regression mismatch in {reference_path.name}: {column}')
            finite = np.isfinite(av) & np.isfinite(bv)
            if finite.any():
                max_error = max(max_error, float(np.abs(av[finite]-bv[finite]).max()))
            numeric_cells += int(finite.sum())
        else:
            require(a.fillna('<MISSING>').astype(str).equals(b.fillna('<MISSING>').astype(str)), f'Regression mismatch in {reference_path.name}: {column}')
    return dict(reference=str(reference_path), rows=len(reference), columns=len(columns), numeric_cells=numeric_cells,
                new_rows_without_historical_reference=new_count, maximum_absolute_error=max_error, absolute_tolerance=1e-9, passed=True)


def verify_reference(reference_root, looking_trials, looking_people, spatial_trials=None, spatial_people=None, proportions=None):
    proportions = {} if proportions is None else proportions
    root = Path(reference_root)
    comparisons = {'looking_participants': compare_table(looking_people, root/'2026-11-04_gaze_extraction_ROI/Looking_Time_JASP_ROI_2026-11-04.csv', ['participant_id'], normalize_condition=True)}
    # Compare scientific trial outputs; old absolute paths and richer diagnostic fields are not inputs.
    # Old trial tables do not contain participant_id; derive the same cross-age unique key.
    ref = pd.read_csv(root/'2026-11-04_gaze_extraction_ROI/trial_results.csv')
    ref['participant_id'] = ref.age_months.astype(str)+'mo_'+ref.participant
    comparison_cols = ['raw_first_ms', 'raw_total_ms', 'first_s', 'total_s', 'validation_ratio',
                       'validation_pass', 'first_pair_retained', 'total_pair_retained']
    selected = ref[ref.participant_id.isin(looking_people.participant_id)].set_index(['participant_id', 'trial']).sort_index()
    actual = looking_trials[looking_trials.participant_id.isin(selected.index.get_level_values('participant_id'))].set_index(['participant_id', 'trial']).sort_index()
    require(selected.index.equals(actual.index), 'Trial reference keys differ')
    for column in comparison_cols:
        require(np.allclose(actual[column].to_numpy(dtype=float), selected[column].to_numpy(dtype=float), atol=1e-9, rtol=0, equal_nan=True), f'Trial regression mismatch: {column}')
    comparisons['looking_trials'] = dict(rows=len(selected), columns=comparison_cols, passed=True)
    if spatial_trials is not None:
        comparisons['spatial_trials'] = compare_table(spatial_trials, root/'2026-11-04_spatial_roi/results/Spatial_ROI_Trial_Results.csv', ['participant_id', 'trial'], ignored=['source'])
        comparisons['spatial_participants'] = compare_table(spatial_people, root/'2026-11-04_spatial_roi/results/Spatial_ROI_JASP_Participants.csv', ['participant_id'])
    for name, table in proportions.items():
        comparisons[name] = compare_table(table, root/f'2026-11-05_spatial_proportion/{name}/Proportion_JASP_Participants.csv', ['participant_id'])
    return comparisons
