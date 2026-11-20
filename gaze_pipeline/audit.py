"""A concise human-readable audit, plus detailed sample/trial records."""
import json

import numpy as np
import pandas as pd

from .common import write_csv, write_json


def termination_table(trials, rules):
    """Describe recording ends; do not infer button presses or exclude trials."""
    rows = []
    for tr in trials.itertuples():
        source_present = pd.notna(tr.source)
        delay = rule_stop = np.nan
        if not source_present:
            status = 'not_assessed_missing_trial'
        elif not tr.validation_pass:
            status = 'not_assessed_validation_failed'
        elif tr.total_status == 'no_measurement_frames':
            status = 'not_assessed_no_measurement_frames'
        elif tr.stop_reason == 'two_second_offscreen':
            rule_stop = tr.analysis_end_ms / 1000
            delay = max(0., (tr.trial_end_ms-tr.analysis_end_ms) / 1000)
            status = 'delayed_termination' if delay > 1e-9 else 'rule_reached_at_recording_end'
        elif tr.stop_reason == 'measurement_end':
            # A configured analysis cap does not establish an early recording end.
            status = 'not_assessed_measurement_cap'
        else:
            status = 'possible_early_termination_review'
        rows.append(dict(participant_id=tr.participant_id, age_months=tr.age_months,
                         group=f'{tr.age_months}mo_{rules["condition_labels"][tr.condition]}',
                         trial=tr.trial, pair_number=tr.pair_number, event=tr.event,
                         status=status, recording_end_s=tr.trial_end_ms/1000,
                         rule_stop_s=rule_stop, delay_s=delay,
                         validation_pass=bool(tr.validation_pass),
                         first_used=bool(tr.first_pair_retained), total_used=bool(tr.total_pair_retained)))
    return pd.DataFrame(rows)


def _records(table):
    # pandas serializes NaN as JSON null and numpy scalars as native numbers.
    return json.loads(table.to_json(orient='records'))


def _trial_names(table):
    return ', '.join(table.sort_values('trial').trial.tolist()) or '—'


def _table(headers, rows):
    def cell(value):
        return str(value).replace('|', '/').replace('\n', ' ')
    return ['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |'] + [
        '| '+' | '.join(cell(v) for v in row)+' |' for row in rows]


def write_audit(trials, people, proportions, config, record, checks, output):
    rules = config['rules']
    present = trials.source.notna()
    terminations = termination_table(trials, rules)
    early = terminations[terminations.status.eq('possible_early_termination_review')]
    delayed = terminations[terminations.status.eq('delayed_termination')]
    exclusions = trials[~trials.first_pair_retained | ~trials.total_pair_retained].copy()
    sample_status = people[['participant_id', 'age_months', 'group', 'first_pairs_retained', 'total_pairs_retained']].copy()
    proportion_reductions = []
    total_pair_counts = people.set_index('participant_id').total_pairs_retained
    for name, table in proportions.items():
        mapping = table.set_index('participant_id').proportion_valid_pair_count
        sample_status[name+'_pairs_retained'] = sample_status.participant_id.map(mapping)
        for person in table.itertuples():
            time_pairs = int(total_pair_counts.loc[person.participant_id])
            ratio_pairs = int(person.proportion_valid_pair_count)
            if ratio_pairs < time_pairs:
                proportion_reductions.append(dict(denominator=name, participant_id=person.participant_id,
                                                  total_time_pairs=time_pairs, proportion_pairs=ratio_pairs))
    summary = {
        'run_id': record['run_id'], 'parameters': rules, 'selection': config['selection'],
        'analyses': record['executed_analyses'], 'paths': config['paths'],
        'participants': {
            'recorded': len(people),
            'with_missing_test_trials': int(trials.loc[~present, 'participant_id'].nunique()),
            'excluded_first': int(people.first_pairs_retained.eq(0).sum()),
            'excluded_total': int(people.total_pairs_retained.eq(0).sum()),
            'first_retained': int(people.first_pairs_retained.gt(0).sum()),
            'total_retained': int(people.total_pairs_retained.gt(0).sum()),
            'group_counts': {str(k): int(v) for k, v in people.groupby('group').size().items()}
        },
        'trials': {
            'expected_slots': len(trials), 'present': int(present.sum()), 'missing': int((~present).sum()),
            'validation_failed': int((present & ~trials.validation_pass).sum()),
            'first_retained': int(trials.first_pair_retained.sum()),
            'total_retained': int(trials.total_pair_retained.sum()),
            'first_present_but_excluded': int((present & ~trials.first_pair_retained).sum()),
            'total_present_but_excluded': int((present & ~trials.total_pair_retained).sum()),
            'total_valid_but_unpaired': int((present & trials.total_status.eq('valid') & ~trials.total_pair_retained).sum())
        },
        'pairs': {metric: {'retained': int(people[f'{metric}_pairs_retained'].sum()),
                           'not_retained': int(len(people)*2-people[f'{metric}_pairs_retained'].sum())}
                  for metric in ['first', 'total']},
        'proportions': {
            name: {'participants_retained': int(table.proportion_valid_pair_count.gt(0).sum()),
                   'participants_excluded': int(table.proportion_valid_pair_count.eq(0).sum()),
                   'pairs_retained': int(table.proportion_valid_pair_count.sum()),
                   'additional_pairs_unavailable_vs_total_time': int(people.total_pairs_retained.sum()-table.proportion_valid_pair_count.sum())}
            for name, table in proportions.items()
        },
        'termination': {
            'status_counts': {str(k): int(v) for k, v in terminations.status.value_counts().items()},
            'possible_early_trials': len(early), 'possible_early_participants': int(early.participant_id.nunique()),
            'delayed_trials': len(delayed), 'delayed_participants': int(delayed.participant_id.nunique()),
            'maximum_delay_s': float(delayed.delay_s.max()) if len(delayed) else None,
            'median_delay_s': float(delayed.delay_s.median()) if len(delayed) else None,
            'note': 'Possible early = recording ends before the total-looking nonlooking rule is observed; review only. Delay = last recorded time minus observed rule-trigger time, including the wait for the rule. No new exclusions; no independent button-press timing.',
            'flagged_trials': _records(terminations[terminations.status.isin(['possible_early_termination_review', 'delayed_termination'])])
        },
        'proportion_pair_reductions': proportion_reductions,
        'verification_passed': bool(checks.get('result_invariants_passed', False)),
        'excluded_or_missing_trials': _records(exclusions),
        'participant_status': _records(sample_status)
    }
    write_csv(terminations, output/'termination_trials.csv')
    write_csv(exclusions, output/'excluded_or_missing_trials.csv')
    write_csv(sample_status, output/'sample_status.csv')
    write_csv(pd.DataFrame(proportion_reductions, columns=['denominator', 'participant_id', 'total_time_pairs', 'proportion_pairs']), output/'proportion_pair_reductions.csv')
    write_json(output/'audit_summary.json', summary)

    t = summary['trials']
    p = summary['participants']
    git = record['git']
    lines = ['# Data extraction audit', '', f'Run ID: `{record["run_id"]}`; start time (UTC): {record["started_utc"]}.',
             f'Code commit: `{git["commit"] or "No commit yet"}`; uncommitted changes at run start: {git["dirty"]}.',
             '', 'The combined table retains every participant. Exclusion means an outcome did not contribute to its summary; missing values are not filled with zero.',
             f'Detailed tables and run records: `details/{record["run_id"]}/`.', '', '## 1. Run parameters', '']
    cap = 'no fixed upper cap' if rules['measurement_end_ms'] is None else f'{rules["measurement_end_ms"]} ms'
    parameters = [
        ['Executed modules', ', '.join(record['executed_analyses'])],
        ['Selected ages / participants', f'{config["selection"]["ages_months"]} / {config["selection"]["participants"] or "all"}'],
        ['Validation window / minimum valid proportion', f'{rules["validation_start_ms"]}–{rules["validation_end_ms"]} ms (inclusive) / {rules["validation_threshold"]:.0%}'],
        ['Measurement window', f'from {rules["measurement_start_ms"]} ms; {cap}'],
        ['State-segment threshold', f'{rules["minimum_segment_ms"]} ms'],
        ['Whole-screen continuous nonlooking stop threshold', f'{rules["terminate_nonlooking_ms"]} ms'],
        ['First-look initial grace', f'{rules["first_look_grace_ms"]} ms'],
        ['Maximum repaired missing gap', f'{rules["missing_gap_max_frames"]} frames'],
        ['Whole-screen ROI', json.dumps(rules['screen_roi'])],
        ['Pairing', f'{rules["test_pairs"]}; retain the chronological complete-pair prefix'],
        ['Condition labels', json.dumps(rules['condition_labels'])]]
    if 'spatial_roi' in record['executed_analyses']:
        parameters += [['Left track ROI', json.dumps(rules['track_rois']['left'])],
                       ['Right track ROI', json.dumps(rules['track_rois']['right'])]]
    if proportions:
        parameters.append(['Proportion denominators', ', '.join(rules['proportion_denominators'])+'; compute trial proportions before averaging the same event'])
    lines += _table(['Parameter', 'Actual value'], parameters)
    if 'pair_looking_time' in record['executed_analyses']:
        lines += ['', 'Pair 1 and Pair 2 are exported separately using the existing first/total trial durations and pair-retention flags. Unretained pairs remain missing; Pair 2 cannot bypass an incomplete Pair 1.']
    lines += ['', f'Input: `{config["paths"]["data_root"]}`', f'Order reference: `{config["paths"]["order_file"]}`',
              f'Output: `{config["paths"]["output_root"]}`', '', '## 2. Samples, missingness and exclusions', '',
              f'**{p["recorded"]} participants** recorded. First-looking outcomes available for {p["first_retained"]}; '
              f'{p["excluded_first"]} have no complete valid first-looking pair. '
              f'Total-looking outcomes available for {p["total_retained"]}; {p["excluded_total"]} have no complete valid total-looking pair.', '',
              f'Expected Test trial slots: {t["expected_slots"]}; observed files: {t["present"]}; '
              f'**missing trials: {t["missing"]}**, affecting {p["with_missing_test_trials"]} participants.',
              f'Validation failed for {t["validation_failed"]} trials. Observed trials excluded from first / total summaries: '
              f'**{t["first_present_but_excluded"]} / {t["total_present_but_excluded"]}**, including invalid trials and valid but unpaired trials. '
              f'The total-looking count includes {t["total_valid_but_unpaired"]} valid but unpaired trials. Missing trials are counted separately.', '']
    group_rows = []
    for group, block in people.groupby('group', sort=True):
        group_rows.append([group, len(block), int(block.first_pairs_retained.gt(0).sum()), int(block.total_pairs_retained.gt(0).sum())])
    lines += _table(['Group', 'Recorded participants', 'First available', 'Total available'], group_rows)
    lines += ['', 'Pair counts by outcome:', '']
    pair_rows = [[metric, value['retained'], value['not_retained']] for metric, value in summary['pairs'].items()]
    lines += _table(['Outcome', 'Retained pairs', 'Pairs not retained (including missing)'], pair_rows)
    if proportions:
        lines += ['', 'Proportion availability:', '']
        lines += _table(['Denominator', 'Participants available', 'Participants unavailable', 'Retained pairs', 'Additional pairs unavailable relative to total time'],
                        [[name, v['participants_retained'], v['participants_excluded'], v['pairs_retained'], v['additional_pairs_unavailable_vs_total_time']]
                         for name, v in summary['proportions'].items()])
        if proportion_reductions:
            lines += ['', 'Participants with fewer proportion pairs than total-time pairs (time outcomes remain available):', '']
            lines += _table(['Denominator', 'Participant', 'Total-time pairs', 'Proportion pairs'],
                            [[v['denominator'], v['participant_id'], v['total_time_pairs'], v['proportion_pairs']]
                             for v in proportion_reductions])
    lines += ['', 'Participants with missing or excluded trials:', '']
    rows = []
    for ident, block in exclusions.groupby('participant_id', sort=False):
        exists = block.source.notna()
        rows.append([ident, _trial_names(block[~exists]), _trial_names(block[exists & ~block.first_pair_retained]),
                     _trial_names(block[exists & ~block.total_pair_retained])])
    lines += _table(['Participant', 'Missing trials', 'Observed but excluded from first', 'Observed but excluded from total'], rows) if rows else ['None.']
    lines += ['', 'See `excluded_or_missing_trials.csv` for trial-level reasons and `sample_status.csv` for participant-level counts in this run\'s details directory.',
              '', '## 3. Early / delayed termination', '',
              f'**Possible early termination, review required: {len(early)} trials in {early.participant_id.nunique()} participants.** '
              f'The recording ended before continuous nonlooking of {rules["terminate_nonlooking_ms"]} ms was observed. '
              'This does not confirm an early button press and does not automatically exclude the trial.', '',
              f'**Recording continued after the rule triggered: {len(delayed)} trials in {delayed.participant_id.nunique()} participants.** '
              'Delay = last recorded timestamp minus rule-trigger timestamp. The trigger already includes the wait for the nonlooking threshold; do not subtract that threshold again.']
    if len(delayed):
        lines += [f'Median positive delay: {delayed.delay_s.median():.3f} s; maximum: {delayed.delay_s.max():.3f} s.']
    lines += ['', 'Flagged trials by participant; an em dash indicates no flag of that type.', '']
    flags = terminations[terminations.status.isin(['possible_early_termination_review', 'delayed_termination'])]
    rows = []
    for ident, block in flags.groupby('participant_id', sort=False):
        e = block[block.status.eq('possible_early_termination_review')]
        d = block[block.status.eq('delayed_termination')]
        rows.append([ident, _trial_names(e), _trial_names(d), f'{d.delay_s.max():.3f}' if len(d) else '—'])
    lines += _table(['Participant', 'Possible early-ending trials', 'Trials with positive delay', 'Maximum delay (s)'], rows) if rows else ['None.']
    unassessed = terminations[terminations.status.str.startswith('not_assessed')]
    lines += ['', 'Missing trials, failed validation, absent measurement frames and configured measurement caps are reported as unassessed rather than as having no early/delayed ending.',
              f'Unassessed status counts: `{json.dumps(unassessed.status.value_counts().to_dict(), ensure_ascii=False)}`.',
              'See `termination_trials.csv` for every trial\'s status, rule-trigger time, recording end, delay and inclusion flags.',
              'This audit adds no early/delay exclusion rule and does not alter extracted looking times. File hashes, environment and numerical checks are in `run_record.json` and `verification.json`.', '']
    (output/'audit.md').write_text('\n'.join(lines), encoding='utf-8')
    return summary
