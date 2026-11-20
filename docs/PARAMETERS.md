# Parameters and measurement definitions

Parameter meanings are written next to their values in the root `config.json`, using `_description...` fields. This document is an optional supplement. Input/output paths are edited only at the top of `main.py`.

All times below are milliseconds unless a column name ends in `_s`. Gaze positions use normalized **screen** coordinates, including the experiment display's black borders. There is no additional video-to-screen coordinate transformation in this pipeline.

## Configuration fields

| Field | Default | Meaning |
|---|---|---|
| `schema_version` | 1 | Configuration schema supported by this program |
| `main.py: INPUT_DIR` | absolute `data_pre` path | Post-processed input directory |
| `main.py: ORDER_FILE` | `INPUT_DIR / 'Gaze-Order.xlsx'` | Reference stimulus orders; CSV also supported |
| `main.py: OUTPUT_DIR` | absolute `Analysis output` path | Latest CSV/audit at top level; complete run snapshots in `details/` |
| `selection.ages_months` | `[8,12]` | Age directories to search |
| `selection.participants` | `[]` | Empty means all; otherwise full IDs such as `8mo_P001` |
| `analyses` | looking_time, pair_looking_time | Existing across-pair means plus separate pair exports; looking_time is the prerequisite |
| `validation_start_ms` / `validation_end_ms` | 7000 / 10000 | Inclusive validation window; denominator is actual observed rows in this window |
| `validation_threshold` | 0.5 | Minimum cleaned looking-flag proportion; equality passes |
| `measurement_start_ms` | 13000 | Inclusive start of looking-time measurement |
| `measurement_end_ms` | null | No fixed upper cap; a numeric value sets an inclusive timestamp cap |
| `minimum_segment_ms` | 400 | Historical state-switch confirmation and accepted segment-duration rule |
| `terminate_nonlooking_ms` | 2000 | Continuous whole-screen non-looking that terminates total-looking measurement |
| `first_look_grace_ms` | 2000 | Historical first-look initial-grace rule; see below |
| `missing_gap_max_frames` | 2 | Supported values 0, 1 or 2; repair short missing-looking flags surrounded by looking, never observed outside-screen points |
| `screen_roi` | X .06–.94, Y .03–.97 | Inclusive whole-screen valid region, used in both validation and measurement |
| `track_rois.left` | X .077–.5, Y .65–.97 | Deferred setting, unused by main.py; left track X maximum excluded |
| `track_rois.right` | X .5–.923, Y .65–.97 | Deferred setting, unused by main.py; right track X maximum included |
| `test_pairs` | `[[1,2],[3,4]]` | Only this reviewed two-pair design is supported by version 0.1 |
| `condition_labels` | Con→CON, Int→INC | Display labels for output tables; reference matching uses original values |
| `proportion_denominators` | roi_total, screen_total | Deferred setting, unused by main.py |

ROI keys `x_min`, `x_max`, `y_min`, `y_max` are coordinate bounds. Track `x_max_inclusive` controls ownership of the right edge; all lower edges and Y upper edges are included. The shared X=.5 edge belongs to the right track only. Overlapping track ROIs are rejected.

The active entry point runs only whole-screen looking time and optional separate-pair exports. Track ROI and proportion source files/settings are preserved for later work, and configuration validation still checks their structure, but main.py does not execute these analyses. The whole-screen ROI is still required for looking-time validity. Conventions 9-14 below document the deferred modules.

## Preserved methodological conventions

These conventions are deliberate code behavior, not interchangeable parameter choices. Changing them requires a reviewed code change and new verification.

1. A raw whole-screen looking flag requires nonmissing `Screen-Space_pupil` plus finite X/Y inside the screen ROI. This is an operational gaze-validity rule, not a new pupil-diameter analysis.
2. Repair changes boolean looking flags, never measured pupil or coordinate values. Single-frame repair runs before two-frame repair, matching the historical code. At 50 Hz, 1–2 frames are approximately 20–40 ms; actual elapsed times always use recorded timestamps.
3. Temporal state changes shorter than 400 ms can be bridged by the historical state machine. Whole-screen time is therefore not simply the count of valid frames times 20 ms. A known outside point is not repaired as missing, but a short state change can still be bridged by the separate temporal rule.
4. Total looking stops when the historical state machine observes the non-looking threshold. First look returns its first accepted looking segment. During first-look non-looking termination, the code uses the grace threshold if the non-looking onset is at or before `measurement_start_ms + first_look_grace_ms`; later onsets use the segment threshold. This is preserved from the old implementation rather than replaced with a new interpretation.
5. Durations use recorded timestamp differences. The final sample receives no extra frame duration. A finite measurement cap is applied before timing and spatial allocation.
6. Whole-screen first/total trial durations must be positive to contribute to their respective participant summaries. Invalid/missing trials remain missing. First and total pair sets are recorded independently; `valid_pair_count` and spatial analyses refer to the **total-looking** pair set.
7. Test1–2 and Test3–4 are complete only when both New and Old events are valid. Retain a chronological complete-pair prefix: an incomplete first pair cannot be bypassed to use the second.
8. Participant whole-screen values are event-specific means across retained trials, then transformed with log10. Track `totalpairs` values are also event-specific means, not sums. Participants with no complete pair remain in the table with missing outcomes and a count of zero.
9. Track dwell is the overlap of actual sample intervals `[time_i,time_i+1)` with accepted whole-screen looking segments. Assign using the current sample's cleaned validity and coordinates. There is no separate 400 ms track-minimum or two-second track-departure termination. Switching tracks does not terminate the trial.
10. Valid unvisited track = **0 seconds**; unavailable trial/pair = missing. Unknown/nonfinite coordinates are not assigned to either track. Other-screen and unassigned accepted time are recorded, so all time components sum to total accepted screen time.
11. In a stimulus filename, `Left`/`Right` identifies the **old** location; the opposite side is the new location. Final `New`/`Old` identifies the event. In a New event, ball=new location; in an Old event, ball=old location.
12. `roi_total`: ball or empty-location seconds divided by their sum within that trial. `screen_total`: ball or empty-location seconds divided by accepted whole-screen total seconds within that trial.
13. Compute each trial's ratio **before** averaging retained same-event trials. A zero denominator makes a ratio unavailable; complete-pair prefix rules are applied again for proportions. Time-based pair counts remain unchanged and proportion-based counts are recorded separately.
14. Zero ratios and zero track times remain zero in raw columns; their log10 columns are blank. No pseudocount is added. Missing values are never filled with zero.
15. Separate-pair exports reuse the existing trial durations and first/total pair-retention flags. They introduce no timing or exclusion rule. An unavailable pair has missing New/Old outcomes for that metric, even if an individual trial has a valid duration. The original event-specific across-pair means must equal the means of the exported retained pair values.

## Column naming

| Pattern | Meaning |
|---|---|
| `new_first_s`, `old_total_s`, etc. | Event-specific participant whole-screen mean seconds |
| `log10_first_new`, etc. | Log10 of the corresponding positive participant mean |
| `first_pairs_retained`, `total_pairs_retained` | Metric-specific pair counts |
| `pair1_valid`, `pair2_valid`, `valid_pair_count` | Total-looking pair eligibility/count |
| `pair1_new_first_s`, `pair2_old_total_s`, etc. | Separate pair whole-screen seconds for the New/Old reveal event |
| `pair1_log10_first_new`, `pair2_log10_total_old`, etc. | Log10 of the corresponding positive separate-pair duration |
| `pair1_first_retained`, `pair2_total_retained`, etc. | Separate pair eligibility for each metric, 1 or 0 |
| `spatial_pair1_eventNew_oldloc_s` | Pair 1, New event, dwell at old location in seconds |
| `spatial_totalpairs_eventOld_newloc_log10` | Log10 of mean new-location dwell during Old events across retained pairs |
| `prop_roi_total_pair1_newgoal_ball_prop` | New event, ball location, track-total denominator, Pair 1 |
| `prop_screen_total_totalpairs_oldgoal_empty_prop` | Mean of Old-event empty-location trial proportions with screen denominator |
| `prop_*_proportion_valid_pair_count` | Pair count available for that denominator's proportions |
| `prop_*_*_s` and `prop_*_*_log10` | Preserved time-based values, whose pair set may differ from ratio eligibility |

The current combined CSV contains the whole-screen columns and selected separate-pair columns. The `spatial_*` and `prop_*` naming patterns above describe deferred analyses and older snapshots. `column_dictionary.json` supplies the exact columns and source module of each run. The verification report distinguishes structural/invariant checks from historical comparisons; neither proves that a scientific rule is the correct choice for the research question.
