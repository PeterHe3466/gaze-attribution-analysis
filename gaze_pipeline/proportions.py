import numpy as np
import pandas as pd

from .common import log10_positive, write_csv

META = ['participant_id', 'age_months', 'condition', 'group', 'order_number',
        'test_sequence', 'valid_pair_count', 'pair1_valid', 'pair2_valid']


def calculate_proportions(spatial_trials, participants, denominator):
    trials = spatial_trials[spatial_trials.pair_retained].copy()
    trials['ball_s'] = np.where(trials.event.eq('New'), trials.new_location_s, trials.old_location_s)
    trials['empty_s'] = np.where(trials.event.eq('New'), trials.old_location_s, trials.new_location_s)
    trials['denominator_s'] = trials.ball_s + trials.empty_s if denominator == 'roi_total' else trials.whole_screen_total_s
    trials['proportion_available'] = trials.denominator_s.gt(0)
    for content in ['ball', 'empty']:
        trials[content+'_prop'] = trials[content+'_s'].div(trials.denominator_s.where(trials.proportion_available))
    wide = participants[META].copy()
    audit_rows = []
    for idx, person in participants.iterrows():
        t = trials[trials.participant_id.eq(person.participant_id)]
        eligible, prefix_ok = {}, True
        for pair in [1, 2]:
            p = t[t.pair_number.eq(pair)]
            ok = prefix_ok and len(p) == 2 and set(p.event) == {'New', 'Old'} and bool(p.proportion_available.all())
            eligible[pair] = prefix_ok = bool(ok)
            wide.loc[idx, f'pair{pair}_proportion_valid'] = int(ok)
        wide.loc[idx, 'proportion_valid_pair_count'] = sum(eligible.values())
        for pair_set in ['pair1', 'pair2', 'totalpairs']:
            nums = [int(pair_set[-1])] if pair_set != 'totalpairs' else [1, 2]
            chosen = [n for n in nums if eligible[n]]
            for event, event_name in [('New', 'newgoal'), ('Old', 'oldgoal')]:
                kept = t[t.pair_number.isin(chosen) & t.event.eq(event)]
                for content, loc in [('ball', 'newloc' if event == 'New' else 'oldloc'), ('empty', 'oldloc' if event == 'New' else 'newloc')]:
                    prefix = f'{pair_set}_{event_name}_{content}'
                    # Seconds retain their original time-based pair set, even when a ratio is undefined.
                    for suffix in ['s', 'log10']:
                        wide.loc[idx, prefix+'_'+suffix] = person[f'{pair_set}_event{event}_{loc}_{suffix}']
                    value = float(kept[content+'_prop'].mean()) if len(kept) else np.nan
                    wide.loc[idx, prefix+'_prop'] = value
                    wide.loc[idx, prefix+'_prop_log10'] = log10_positive(value)
                    audit_rows.append(dict(participant_id=person.participant_id, pair_set=pair_set, event=event,
                                           content=content, contributing_trials=';'.join(kept.trial.tolist()),
                                           proportion_pair_count=len(chosen), proportion=value))
    for name in ['pair1_proportion_valid', 'pair2_proportion_valid', 'proportion_valid_pair_count']:
        wide[name] = wide[name].astype(int)
    return wide, trials, pd.DataFrame(audit_rows)


def extract_proportions(spatial_trials, participants, rules, output):
    results = {}
    for denominator in rules['proportion_denominators']:
        wide, trials, aggregation = calculate_proportions(spatial_trials, participants, denominator)
        write_csv(wide, output / f'proportions_{denominator}_participants.csv')
        write_csv(trials, output / f'proportions_{denominator}_trials.csv')
        write_csv(aggregation, output / f'proportions_{denominator}_aggregation.csv')
        results[denominator] = wide
    return results
