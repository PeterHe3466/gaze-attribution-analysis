# Gaze attribution: reproducible feature extraction

This project converts **post-processed, per-trial gaze CSVs** into analysis-ready participant tables. Its single entry point is `main.py`.

The current entry point extracts Test-phase first/total whole-screen looking time, both averaged across retained pairs and separately for Pair 1 and Pair 2. Track ROI dwell and proportion analyses are deferred: their source files and settings are retained, but `main.py` does not import, execute or merge their results. Pupillo export, developer-provided pupil filtering, pupil-change analysis, inferential statistics and plotting remain outside this entry point. Familiarization files verify stimulus order, not familiarization outcomes.

For a short introduction, see [START_HERE.md](START_HERE.md).

## Run

The project uses Python 3.12. A resolved dependency graph is in `uv.lock`.

From this directory, in PowerShell or another terminal:

```powershell
uv sync --frozen --cache-dir .uv-cache
uv run --frozen --cache-dir .uv-cache python main.py
```

No virtual-environment activation or Git Bash is required. On this computer, `.venv` has already been installed and can also be used directly:

```powershell
.\.venv\Scripts\python.exe main.py
```

Edit `INPUT_DIR`, `ORDER_FILE` and `OUTPUT_DIR` at the top of `main.py`. They currently read the existing `data_pre` inputs and write to the separate `Analysis output` directory. Paths are not stored in the JSON configuration.

The root-level `config.json` contains the analysis settings and English explanations adjacent to each parameter. Fields beginning with `_description` are documentation and are ignored during calculation. To use an alternative settings file:

```powershell
uv run --frozen --cache-dir .uv-cache python main.py --config my_analysis.json
```

To validate a configuration without processing data:

```powershell
uv run --frozen --cache-dir .uv-cache python main.py --check-config
```

## Inputs

```text
data_pre/
  Gaze-Order.xlsx
  8mo_data_pre/
    P001_preprocessed/
      001_Fami1.csv ... 001_Fami4.csv
      001_Gaze_Test1.csv ... 001_Gaze_Test4.csv
  12mo_data_pre/
    P001_preprocessed/ ...
```

Each participant is identified by age **and** participant number (for example, `8mo_P001`). Missing Test trials are represented explicitly; they are never filled with zero. The order reference can be `.xlsx` or `.csv` with the same column names.

Required Test CSV columns: `frame_no`, `frame_time` (milliseconds), `filtered_gaze_pos_x`, `filtered_gaze_pos_y` (normalized screen coordinates), `Screen-Space_pupil`, `stimulus_file`, `trial_label`, and `subject_code`. Timestamps and frame numbers must be finite, unique and increasing. The pipeline checks stimulus order, participant identity, trial labels and duplicate trial files before accepting results.

## Structure

| File/module | Responsibility |
|---|---|
| `main.py` | Input/output paths, module execution, combined table and run recording |
| `config.json` | Participant selection, windows, thresholds and ROI definitions, with explanations |
| `gaze_pipeline/inputs.py` | Discover sessions and verify stimulus order and input structure |
| `gaze_pipeline/quality.py` | Whole-screen frame validity and short missing-gap flag repair |
| `gaze_pipeline/timing.py` | Historical first/total looking-time state machines |
| `gaze_pipeline/looking_time.py` | Trial extraction and chronological complete-pair aggregation |
| `gaze_pipeline/pair_looking_time.py` | Export Pair 1 and Pair 2 separately from existing trial durations and retention flags |
| `gaze_pipeline/spatial_roi.py` | Deferred track ROI module, retained but disconnected from `main.py` |
| `gaze_pipeline/proportions.py` | Deferred proportion module, retained but disconnected from `main.py` |
| `gaze_pipeline/provenance.py` | Code/data hashes, Git state and environment records |
| `gaze_pipeline/verification.py` | Result invariants and optional historical comparison |
| `gaze_pipeline/audit.py` | Concise parameters/sample/exclusion/termination audit |
| `docs/PARAMETERS.md` | Optional supplement on fixed methodological conventions |

The active dependency is `looking_time → pair_looking_time`. `config.json` selects both by default; selecting only `pair_looking_time` still runs its looking-time prerequisite. Selecting only `looking_time` exports the existing averages without separate-pair columns. Track ROI and proportion names are no longer accepted by this entry point. Their saved settings are not applied to the active extraction. The whole-screen validity ROI remains part of the established looking-time rules.

To add an analysis, add a module, register/call it and merge its uniquely named outputs in `main.py`, and select it in a configuration. Avoid editing existing extraction modules unless intentionally changing their behavior.

## Separate pair outcomes

Pair 1 contains Test1-2; Pair 2 contains Test3-4. The new module reuses `looking_time_trials.csv`; it does not recalculate or change trial timing, validation or exclusion rules. New and Old identify the reveal **event**, not a left/right ROI.

- `pair1_new_first_s`, `pair1_old_first_s`, `pair1_new_total_s`, `pair1_old_total_s`: Pair 1 outcomes in seconds.
- The corresponding `pair2_*` columns: Pair 2 outcomes in seconds.
- `pair1_log10_first_new`, `pair2_log10_total_old`, etc.: log10 of the corresponding positive duration.
- `pair1_first_retained`, `pair1_total_retained`, and the Pair 2 equivalents: metric-specific eligibility, 1 or 0.

Both New and Old trials must qualify for a metric. An unretained pair has missing outcomes, not zeros. An incomplete Pair 1 cannot be bypassed to retain Pair 2. First and total looking retain their own pair sets. The existing across-pair means stay in the combined CSV and are checked against the means of the separate pair values.

## Outputs and audit records

The separate `Analysis output` directory has just two primary files and a details directory:

```text
Analysis output/
  analysis_ready.csv
  audit.md
  details/
    <UTC timestamp>_<unique ID>/
      analysis_ready.csv
      audit.md
      ...component tables, manifests, logs and run records...
```

The two top-level files are updated after a successful run. Complete per-run snapshots remain in `details/`; failed runs do not publish a new top-level result.

- `analysis_ready.csv`: the combined participant table, one row per selected participant, with the existing whole-screen averages and the selected separate-pair columns. Current runs contain no track ROI or proportion columns; older complete runs remain in `details/`.
- `audit.md`: actual parameters, participant/trial/pair inclusion and missingness, and IDs/trials with possible early or delayed recording ends. Possible early means the recording ended before the nonlooking stop rule was observed; it is a review flag, not a confirmed button press or new exclusion.

Within each `details/<run ID>/` snapshot:

- `looking_time_trials.csv`, `looking_time_participants.csv`: existing trial decisions and participant averages.
- `pair_looking_time_participants.csv`: separate pair outcomes in participant-wide format.
- `pair_looking_time_pairs.csv`: one row per participant and pair, including missing outcomes and retention reasons; both pair slots are always represented.
- `termination_trials.csv`, `excluded_or_missing_trials.csv`, `sample_status.csv`, `audit_summary.json`: detailed audit records.
- `column_dictionary.json`: column name, type and source module; see `docs/PARAMETERS.md` for naming and scientific meaning.
- `config_requested.json` and `config_resolved.json`: the exact requested settings and resolved input/output paths.
- `input_manifest.json`, `code_manifest.json`: input and source SHA-256 checksums.
- `run_record.json`: success/failure, invocation, Python/package/platform versions, Git commit and dirty status, and output hashes.
- `verification.json`: completed checks; historical comparisons appear only when explicitly requested.
- `total_looking_segments.log`, `first_looking_segments.log`: detailed timing records.

Only runs with `run_record.json` reporting `status: success` are complete. A failed run's partial tables are diagnostic artifacts. A parameter-description document explains a rule; the run record and saved configuration establish which rule was actually used.

## Verify

```powershell
uv run --frozen --cache-dir .uv-cache python -m unittest discover -s tests -v
```

For the original configuration, optionally compare with the existing dated results:

```powershell
uv run --frozen --cache-dir .uv-cache python main.py --reference-root ../Codex
```

This comparison checks the existing whole-screen participant/trial outputs; deferred track ROI and proportion results are not compared by `main.py`. It is for refactor verification, not a permanent dependency. Current inputs contain 58 participants; the historical tables contain 53. Historical checks cover overlapping participants only and explicitly count additional rows without a historical reference. All current participants undergo input and result checks, including agreement between pair exports, trial values and the existing across-pair means. If changing scientific parameters, do not expect historical comparisons to pass.

## Sharing and preservation

The Git repository contains source, configuration, tests, documentation and the dependency lock. Input data and current generated runs are outside this source directory. Data sharing is a separate decision; post-processing alone does not establish permission to publish participant data.

For each result to preserve, retain its complete successful run directory and the corresponding source commit and `uv.lock`. Document restricted laboratory processing upstream of these post-processed inputs separately; this repository's reproduction boundary starts at the post-processed CSV files.

See [the Git guide](docs/VERSION_CONTROL.md) for local commits, branches, GitHub publishing and code archives. This repository does not claim to preregister any already completed processing choices.
