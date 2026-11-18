"""Historical timing algorithms with explicit per-run rules.

Migrated from the reviewed 2026-11-04 source snapshots. Calculation
branches are preserved; total-looking segments are also returned as
structured metadata so spatial extraction never parses text logs.
"""

import numpy as np

from .quality import check_validation_period, clean_pupil_artifacts

def process_totalLT(trial_data, participant_id, trial_label, validation_stats, debug_file, rules):
    """Historical total looking-time state machine; see docs/PARAMETERS.md."""
    debug_output = []

    def log_debug(message):
        debug_output.append(message)
        debug_file.write(message + '\n')

    def log_total_and_return(total_time):
        log_debug(f'-> Total looking time: {total_time}ms')
        return total_time
    log_debug(f'\n=== P{participant_id}-{trial_label} ===')
    passes_validation, valid_proportion = check_validation_period(trial_data, rules)
    validation_stats.append({'participant_id': participant_id, 'trial_label': trial_label, 'valid_proportion': valid_proportion, 'passed': passes_validation, 'failure_reason': 'insufficient_valid_data' if not passes_validation else None, 'late_termination_ms': 0, 'accepted_segments_ms': [], 'termination_time_ms': None})
    if not passes_validation:
        log_debug(f'Failed validation check (valid proportion: {valid_proportion:.1%})')
        return log_total_and_return(np.nan)
    trial_data = trial_data[(trial_data['frame_time'] >= rules['measurement_start_ms']) & (trial_data['frame_time'] <= (float('inf') if rules['measurement_end_ms'] is None else rules['measurement_end_ms']))].copy().sort_values('frame_time')
    if trial_data.empty:
        log_debug('No data in measurement period')
        return log_total_and_return(0.0)
    trial_data, artifacts_fixed = clean_pupil_artifacts(trial_data, rules)
    if artifacts_fixed > 0:
        log_debug(f'Filled {artifacts_fixed} isolated NA frames')
    total_looking_time = 0.0
    current_segment_type = None
    segment_start_time = None
    segment_start_frame = None
    potential_switch_time = None
    potential_switch_frame = None
    last_frame_time = None
    last_frame_no = None
    continuous_na_start = None
    for _, row in trial_data.iterrows():
        current_time = row['frame_time']
        current_frame = row['frame_no']
        is_looking = row['is_looking']
        if segment_start_time is None:
            segment_start_time = current_time
            segment_start_frame = current_frame
            current_segment_type = 'valid' if is_looking else 'NA'
            if not is_looking:
                continuous_na_start = current_time
        elif is_looking != (current_segment_type == 'valid'):
            if potential_switch_time is None:
                potential_switch_time = current_time
                potential_switch_frame = current_frame
            opposite_duration = current_time - potential_switch_time
            if opposite_duration >= rules['minimum_segment_ms']:
                segment_duration = potential_switch_time - segment_start_time
                if segment_duration >= rules['minimum_segment_ms'] and current_segment_type == 'valid':
                    total_looking_time += segment_duration
                    validation_stats[-1]['accepted_segments_ms'].append((float(segment_start_time), float(potential_switch_time)))
                    log_debug(f'Added valid segment: {segment_duration:.0f}ms (frames {segment_start_frame}-{potential_switch_frame - 1})')
                segment_start_time = potential_switch_time
                segment_start_frame = potential_switch_frame
                current_segment_type = 'valid' if is_looking else 'NA'
                if not is_looking:
                    continuous_na_start = potential_switch_time
                potential_switch_time = None
                potential_switch_frame = None
        else:
            potential_switch_time = None
            potential_switch_frame = None
            if is_looking:
                continuous_na_start = None
        if not is_looking:
            if continuous_na_start is None:
                continuous_na_start = current_time
            na_duration = current_time - continuous_na_start
            if na_duration >= rules['terminate_nonlooking_ms']:
                if current_segment_type == 'valid' and continuous_na_start - segment_start_time > 0:
                    final_valid_duration = continuous_na_start - segment_start_time
                    if final_valid_duration >= rules['minimum_segment_ms']:
                        total_looking_time += final_valid_duration
                        validation_stats[-1]['accepted_segments_ms'].append((float(segment_start_time), float(continuous_na_start)))
                        log_debug(f'Added valid segment: {final_valid_duration:.0f}ms (frames {segment_start_frame}-{last_frame_no})')
                validation_stats[-1]['termination_time_ms'] = float(current_time)
                actual_end_time = trial_data['frame_time'].iloc[-1]
                late_termination_time = actual_end_time - current_time
                if late_termination_time > 0:
                    validation_stats[-1]['late_termination_ms'] = late_termination_time
                    log_debug(f'Terminating on {na_duration:.0f}ms NA (late manual termination: {late_termination_time:.0f}ms)')
                else:
                    log_debug(f'Terminating on {na_duration:.0f}ms NA')
                return log_total_and_return(total_looking_time)
        last_frame_time = current_time
        last_frame_no = current_frame
    if current_segment_type == 'valid':
        final_end_time = potential_switch_time if potential_switch_time else last_frame_time
        final_end_frame = potential_switch_frame if potential_switch_frame else last_frame_no
        final_duration = final_end_time - segment_start_time
        if final_duration >= rules['minimum_segment_ms']:
            total_looking_time += final_duration
            validation_stats[-1]['accepted_segments_ms'].append((float(segment_start_time), float(final_end_time)))
            last_included_frame = final_end_frame - 1 if potential_switch_frame else final_end_frame
            log_debug(f'Added final valid segment: {final_duration:.0f}ms (frames {segment_start_frame}-{last_included_frame})')
    return log_total_and_return(total_looking_time)

def process_firstLook(trial_data, participant_id, trial_label, validation_stats, debug_file, rules):
    """Historical first-looking-time state machine; see docs/PARAMETERS.md."""

    def log_debug(message):
        debug_file.write(message + '\n')

    def log_and_return(val):
        log_debug(f'-> First look time: {val}ms')
        return val
    log_debug(f'\n=== P{participant_id}-{trial_label} ===')
    passes_validation, valid_proportion = check_validation_period(trial_data, rules)
    validation_stats.append({'participant_id': participant_id, 'trial_label': trial_label, 'valid_proportion': valid_proportion, 'passed': passes_validation, 'failure_reason': 'insufficient_valid_data' if not passes_validation else None, 'late_termination_ms': 0})
    if not passes_validation:
        log_debug(f'Failed validation check (valid proportion: {valid_proportion:.1%})')
        return log_and_return(np.nan)
    trial_data = trial_data[(trial_data['frame_time'] >= rules['measurement_start_ms']) & (trial_data['frame_time'] <= (float('inf') if rules['measurement_end_ms'] is None else rules['measurement_end_ms']))].copy().sort_values('frame_time')
    if trial_data.empty:
        log_debug('No data in measurement period')
        return log_and_return(0.0)
    trial_data, artifacts_fixed = clean_pupil_artifacts(trial_data, rules)
    if artifacts_fixed > 0:
        log_debug(f'Filled {artifacts_fixed} isolated NA frames')
    current_segment_type = None
    segment_start_time = None
    segment_start_frame = None
    potential_switch_time = None
    potential_switch_frame = None
    last_frame_time = None
    last_frame_no = None
    continuous_na_start = None
    grace_period_end = rules['measurement_start_ms'] + rules['first_look_grace_ms']
    first_look_time = 0.0
    for _, row in trial_data.iterrows():
        current_time = row['frame_time']
        current_frame = row['frame_no']
        is_looking = row['is_looking']
        if segment_start_time is None:
            segment_start_time = current_time
            segment_start_frame = current_frame
            current_segment_type = 'valid' if is_looking else 'NA'
            if not is_looking:
                continuous_na_start = current_time
        elif is_looking != (current_segment_type == 'valid'):
            if potential_switch_time is None:
                potential_switch_time = current_time
                potential_switch_frame = current_frame
            opposite_duration = current_time - potential_switch_time
            if opposite_duration >= rules['minimum_segment_ms']:
                segment_duration = potential_switch_time - segment_start_time
                if current_segment_type == 'valid' and segment_duration >= rules['minimum_segment_ms']:
                    first_look_time = float(segment_duration)
                    log_debug(f'First valid segment accepted: {segment_duration:.0f}ms (frames {segment_start_frame}-{potential_switch_frame - 1})')
                    return log_and_return(first_look_time)
                segment_start_time = potential_switch_time
                segment_start_frame = potential_switch_frame
                current_segment_type = 'valid' if is_looking else 'NA'
                if not is_looking:
                    continuous_na_start = potential_switch_time
                potential_switch_time = None
                potential_switch_frame = None
        else:
            potential_switch_time = None
            potential_switch_frame = None
            if is_looking:
                continuous_na_start = None
        if not is_looking:
            if continuous_na_start is None:
                continuous_na_start = current_time
            na_duration = current_time - continuous_na_start
            in_grace_period = continuous_na_start <= grace_period_end
            termination_threshold = rules['first_look_grace_ms'] if in_grace_period else rules['minimum_segment_ms']
            if na_duration >= termination_threshold:
                if current_segment_type == 'valid' and continuous_na_start - segment_start_time > 0:
                    final_valid_duration = continuous_na_start - segment_start_time
                    if final_valid_duration >= rules['minimum_segment_ms']:
                        first_look_time = float(final_valid_duration)
                        log_debug(f'First valid segment terminated by NA: {final_valid_duration:.0f}ms (frames {segment_start_frame}-{last_frame_no})')
                        return log_and_return(first_look_time)
                actual_end_time = trial_data['frame_time'].iloc[-1]
                late_termination_time = actual_end_time - current_time
                if late_termination_time > 0:
                    validation_stats[-1]['late_termination_ms'] = late_termination_time
                log_debug(f'Terminating on {na_duration:.0f}ms NA')
                return log_and_return(0.0)
        last_frame_time = current_time
        last_frame_no = current_frame
    if current_segment_type == 'valid':
        final_end_time = potential_switch_time if potential_switch_time else last_frame_time
        final_end_frame = potential_switch_frame if potential_switch_frame else last_frame_no
        final_duration = final_end_time - segment_start_time
        if final_duration >= rules['minimum_segment_ms']:
            first_look_time = float(final_duration)
            last_included_frame = final_end_frame - 1 if potential_switch_frame else final_end_frame
            log_debug(f'Final valid segment used as first look: {final_duration:.0f}ms (frames {segment_start_frame}-{last_included_frame})')
            return log_and_return(first_look_time)
    return log_and_return(0.0)
