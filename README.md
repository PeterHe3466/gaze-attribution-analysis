# Gaze attribution: reproducible feature extraction

This project converts **post-processed, per-trial gaze CSVs** into analysis-ready participant tables. Its single entry point is `main.py`.

The current version extracts Test-phase first/total whole-screen looking time, left/right track dwell time, and proportions using both track-total and whole-screen denominators. Pupillo export, developer-provided pupil filtering, pupil-change analysis, inferential statistics and plotting are outside this version's processing scope. Familiarization files are used to verify stimulus order, not to extract familiarization outcomes.

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
| `gaze_pipeline/spatial_roi.py` | Allocate accepted screen-looking intervals to track ROIs |
| `gaze_pipeline/proportions.py` | Trial-level proportions and participant aggregation |
| `gaze_pipeline/provenance.py` | Code/data hashes, Git state and environment records |
| `gaze_pipeline/verification.py` | Result invariants and optional historical comparison |
| `gaze_pipeline/audit.py` | Concise parameters/sample/exclusion/termination audit |
| `docs/PARAMETERS.md` | Optional supplement on fixed methodological conventions |

The dependencies are `looking_time → spatial_roi → proportions`. Selecting a later module automatically runs its prerequisites. To add an analysis, add a module, register/call it and merge its uniquely named outputs in `main.py`, and select it in a configuration. Avoid editing existing extraction modules unless intentionally changing their behavior.

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

- `analysis_ready.csv`: the combined participant table, one row per selected participant. It currently has 146 columns with all three analyses and both denominators enabled.
- `audit.md`: actual parameters, participant/trial/pair inclusion and missingness, and IDs/trials with possible early or delayed recording ends. Possible early means the recording ended before the nonlooking stop rule was observed; it is a review flag, not a confirmed button press or new exclusion.

Within each `details/<run ID>/` snapshot:

- `looking_time_*`, `spatial_roi_*`, `proportions_*`: component tables, including trial-level decisions.
- `termination_trials.csv`, `excluded_or_missing_trials.csv`, `sample_status.csv`, `audit_summary.json`: detailed audit records.
- `column_dictionary.json`: column name, type and source module; see `docs/PARAMETERS.md` for naming and scientific meaning.
- `config_requested.json` and `config_resolved.json`: the exact requested settings and resolved input/output paths.
- `input_manifest.json`, `code_manifest.json`: input and source SHA-256 checksums.
- `run_record.json`: success/failure, invocation, Python/package/platform versions, Git commit and dirty status, and output hashes.
- `verification.json`: completed checks; historical comparisons appear only when explicitly requested.
- `accepted_screen_looking_segments.csv`, compressed frame assignments, and first/total segment logs: detailed extraction records.

Only runs with `run_record.json` reporting `status: success` are complete. A failed run's partial tables are diagnostic artifacts. A parameter-description document explains a rule; the run record and saved configuration establish which rule was actually used.

## Verify

```powershell
uv run --frozen --cache-dir .uv-cache python -m unittest discover -s tests -v
```

For the original configuration, optionally compare with the existing dated results:

```powershell
uv run --frozen --cache-dir .uv-cache python main.py --reference-root ../Codex
```

This comparison is for refactor verification, not a permanent dependency. Current inputs contain 58 participants; the historical tables contain 53. Historical checks cover overlapping participants only and explicitly count additional rows without a historical reference. All current participants undergo the pipeline's input and result checks. If changing scientific parameters, do not expect the historical result comparison to pass.

## Sharing and preservation

The Git repository contains source, configuration, tests, documentation and the dependency lock. Input data and current generated runs are outside this source directory. Data sharing is a separate decision; post-processing alone does not establish permission to publish participant data.

For each result to preserve, retain its complete successful run directory and the corresponding source commit and `uv.lock`. Document restricted laboratory processing upstream of these post-processed inputs separately; this repository's reproduction boundary starts at the post-processed CSV files.

See [the Git guide](docs/VERSION_CONTROL.md) for local commits, branches, GitHub publishing and code archives. This repository does not claim to preregister any already completed processing choices.
