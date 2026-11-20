"""Export separate pairs using the existing whole-screen looking-time decisions."""
import numpy as np
import pandas as pd

from .common import log10_positive, require, retained_prefix, write_csv


METADATA = ['participant_id', 'age_months', 'participant', 'condition', 'group',
            'order_number', 'test_sequence']


def calculate_pair_looking_time(trials, people, rules):
    """Return participant-wide and participant/pair tables without retiming trials.

    Pair eligibility is inherited separately for first and total looking. An
    unretained pair has missing outcomes even if one of its trials is valid.
    """
    require(people.participant_id.is_unique, 'Duplicate participants in pair export')
    require(set(trials.participant_id) == set(people.participant_id),
            'Participant mismatch in pair export')
    pair_numbers = list(range(1, len(rules['test_pairs']) + 1))
    wide_rows, pair_rows = [], []
    grouped = {ident: block for ident, block in trials.groupby('participant_id', sort=False)}
    for person in people.to_dict('records'):
        metadata = {key: person[key] for key in METADATA}
        result = metadata.copy()
        block = grouped[person['participant_id']]
        require(set(block.pair_number) == set(pair_numbers), 'Unexpected pair numbers')
        retained = {metric: [] for metric in ['first', 'total']}
        for number in pair_numbers:
            pair = block[block.pair_number.eq(number)]
            require(len(pair) == 2 and set(pair.event) == {'New', 'Old'},
                    'Each pair must contain exactly one New and one Old trial')
            pair_row = {**metadata, 'pair_number': number}
            for metric in ['first', 'total']:
                flag = f'{metric}_pair_retained'
                require(pair[flag].isin([True, False]).all() and pair[flag].nunique() == 1,
                        f'Inconsistent {metric} pair-retention flags')
                kept = bool(pair[flag].iloc[0])
                reason = f'{metric}_pair_reason'
                require(pair[reason].nunique(dropna=False) == 1,
                        f'Inconsistent {metric} pair-retention reasons')
                result[f'pair{number}_{metric}_retained'] = int(kept)
                pair_row[flag] = kept
                pair_row[reason] = pair[reason].iloc[0]
                if kept:
                    values = pair[f'{metric}_s'].to_numpy(dtype=float)
                    require((np.isfinite(values) & (values > 0)).all(),
                            f'Retained {metric} pair contains invalid durations')
                    retained[metric].append(number)
                for event in ['New', 'Old']:
                    value = float(pair.loc[pair.event.eq(event), f'{metric}_s'].iloc[0]) if kept else np.nan
                    raw_column = f'{event.lower()}_{metric}_s'
                    log_column = f'log10_{metric}_{event.lower()}'
                    result[f'pair{number}_{raw_column}'] = pair_row[raw_column] = value
                    result[f'pair{number}_{log_column}'] = pair_row[log_column] = log10_positive(value)
            pair_rows.append(pair_row)
        for metric, kept in retained.items():
            require(kept == retained_prefix(kept, pair_numbers),
                    'Pair 2 cannot be retained when Pair 1 is not retained')
            require(len(kept) == person[f'{metric}_pairs_retained'],
                    f'{metric} pair count differs from looking-time summary')
        wide_rows.append(result)
    return pd.DataFrame(wide_rows), pd.DataFrame(pair_rows)


def extract_pair_looking_time(trials, people, rules, output):
    """Save both pair layouts and return participant-level columns for the main CSV."""
    wide, pairs = calculate_pair_looking_time(trials, people, rules)
    write_csv(wide, output / 'pair_looking_time_participants.csv')
    write_csv(pairs, output / 'pair_looking_time_pairs.csv')
    return wide
