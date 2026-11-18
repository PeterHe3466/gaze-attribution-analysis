# Script review and refactoring record

The selected scope is the latest whole-screen looking-time extraction, left/right track ROI dwell and both proportion denominators. Pupil-change analysis is deferred.

## Older scripts and their roles

| Original location | Role and status |
|---|---|
| `data_preparation_and_extraction/1_merge_separate_trials.py` | Participant trial merging; depends on the missing `analysis_config.py` and includes Habituation/Switch first/last label logic |
| `data_preparation_and_extraction/3_merge_all.py` | Merges participant `_ready.csv` files; also depends on the missing configuration |
| `data_preparation_and_extraction/5_LT_extraction.py` | Original total-looking extraction and aggregation; combines path/configuration dependencies, algorithms and export |
| `data_preparation_and_extraction/6_firstLook_extraction.py` | Original first-looking extraction and aggregation with similar mixed responsibilities |
| `Codex/2026-11-04_gaze_extraction_ROI/` | Adopted whole-screen ROI extraction; hard-coded old-machine `D:/...` paths, AST loading of saved timing functions and replacement of frame-validity functions |
| `Codex/2026-11-04_spatial_roi/extract_track_roi.py` | Adopted v2 track dwell extraction; depends on the previous directory's outputs, source hashes and text logs, and executes at module import |
| `Codex/2026-11-05_spatial_proportion/analyze_proportion.py` | Mixes proportion extraction with statistical tests and depends on saved spatial outputs |
| `Codex/2026-11-04_border_corrected/` | Explicitly stopped draft; its rules are not used |
| `Codex/2026-10-15_pupil_analysis/` and related runs | Historical pupil analysis, outside this migration's extraction scope |

The newer dated runs already contained parameters, input hashes, algorithm checks and result comparisons. The main integration gaps were separate entry points, duplicated parameters, old absolute paths, dependencies on dated result directories/text logs and the lack of a unified source-version baseline.

## Current implementation

- `main.py` is the single entry point. Historical result directories are optional verification references, not calculation inputs.
- Root-level `config.json` supplies parameters and adjacent `_description...` explanations. Documentation is supplementary. Input, order-reference and output paths are defined at the top of `main.py`.
- Historical timing branches are preserved with explicit rule arguments, removing runtime AST/exec and missing-configuration dependencies.
- Whole-screen timing returns structured accepted segments; track extraction uses these directly instead of parsing logs.
- The pipeline reads post-processed single-trial CSVs without writing new `_ready.csv` files into the input directory or changing measured values.
- Feature extraction is separate from inferential testing and plotting.
- `Analysis output` contains the latest combined CSV and concise audit. Component tables and complete run copies, including hashes, settings, environment and Git state, are retained in `details/<run ID>/`.
- Failed runs record `status: failed` and error details; their partial tables are diagnostic artifacts.

Input checks reject duplicate trials, ambiguous order matching, stimulus/participant mismatches and repeated or reversed timestamps/frame numbers. They stop processing for review rather than silently repairing source inputs.

## Numerical verification scope

Current inputs contain 58 participants; historical reference tables contain 53. With `--reference-root ../Codex`:

- Compare whole-screen first/total outcomes, validation and pair decisions, spatial trial/participant tables and both proportion participant tables for the overlapping 53 participants.
- Use absolute tolerance `1e-9`, relative tolerance zero, and compare missing positions and categorical labels.
- Explicitly count rows without a historical reference. New participants still undergo input, timing/spatial accounting, pair-mean and proportion-range checks.
- Matching saved results establishes preservation of their computation behavior; it does not independently validate every scientific method choice.

Each run's `verification.json` contains its detailed checks. A past report does not establish that a later code change is correct.

## Extending the project

Use a separately named configuration when changing windows or ROIs, retaining the earlier configuration and run. Document the reason for scientific-rule changes.

To add an outcome, create a module, add its name to `SUPPORTED_ANALYSES` in `main.py`, add the call and distinct output-column prefixes, and select it in the configuration. Recheck affected existing modules when changing shared inputs or functions; separate script files alone do not guarantee unchanged results.

Fami outcomes, other phases and new pairing designs need their own defined rules. Test-phase windows and pair rules are not automatically applied to every phase.

The laboratory retains upstream software versions, settings, session mapping and actual exception-handling records. This repository's reproduction boundary starts at the post-processed CSV files.
