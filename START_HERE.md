# Start here

This project uses one entry point, one configuration file and separate extraction modules. The source directory is `Demo Gaze attribution/Analysis`.

## Run the pipeline

Open PowerShell in this directory. A Python 3.12 virtual environment and its dependencies are already installed on this computer:

```powershell
.\.venv\Scripts\python.exe main.py
```

Alternatively, use the locked environment through uv:

```powershell
uv run --frozen --cache-dir .uv-cache python main.py
```

Run only `main.py` for normal processing. Edit `INPUT_DIR`, `ORDER_FILE` and `OUTPUT_DIR` at the top of that file. The current input is `data_pre`; results are written to the separate `Analysis output` directory:

```text
Analysis output/
  analysis_ready.csv    Latest successful combined participant table
  audit.md              Latest successful concise audit
  details/
    <run ID>/           Complete run copy, component tables, logs and records
```

The two top-level files are updated after a successful run. Each complete run copy remains in `details`. A run is complete when its `run_record.json` reports `status: success`.

## Where to make changes

| Change | Location |
|---|---|
| Select ages or participants | `selection` in `config.json` |
| Set input, order-reference or output paths | The three path definitions at the top of `main.py` |
| Set validation/measurement windows, thresholds or ROIs | `rules` in `config.json` |
| Select existing analyses | `analyses` in `config.json` |
| Read parameter meanings and units | Adjacent `_description...` fields in `config.json`; the parameter document is supplementary |
| Add an extraction outcome | Add a module, register/call it and merge its outputs in `main.py` |
| Learn the Git workflow | `docs/VERSION_CONTROL.md` |
| Understand the migration from older scripts | `docs/REFACTOR_REVIEW.md` |

`participants: []` selects all participants in the chosen age directories. To select individuals, use complete IDs such as `["8mo_P001", "12mo_P001"]`; age is part of the unique identifier.

`measurement_end_ms: null` applies no fixed upper cap; the continuous nonlooking stop rule still applies. The configuration contains both values and explanations. `_description...` fields do not affect calculations. Each run saves the requested configuration and the resolved paths from `main.py`.

## What the audit contains

`audit.md` has three sections: actual run parameters; samples, missingness and exclusions; and early/delayed termination. Participant, trial and pair counts are reported separately.

A recording that ends before the whole-screen nonlooking rule is observed is flagged as **possible early termination, review required**. A recording that continues after the rule triggers has a positive delay. Neither flag adds an automatic exclusion rule.

## Current extraction scope

The pipeline extracts Test-phase whole-screen first/total looking time. `looking_time.py` supplies the existing across-pair averages; `pair_looking_time.py` also exports Pair 1 and Pair 2 separately. Fami files verify stimulus order. Track ROI and proportion modules are retained for later work but disconnected from `main.py`; pupil-change analysis, laboratory Pupillo preprocessing, inferential tests and plotting also remain outside this entry point.

`config.json` selects `looking_time` and `pair_looking_time` by default. The main CSV includes columns such as `pair1_new_total_s` and `pair2_old_first_s`, plus log10 values and metric-specific retention flags. Each run's details directory also contains `pair_looking_time_participants.csv` and `pair_looking_time_pairs.csv` (one row per participant/pair).

The whole-screen ROI, timing, validation and pair rules remain unchanged. Pair 1 = Test1-2 and Pair 2 = Test3-4. An incomplete first pair still prevents using the second; first and total looking use their own retention decisions. Unretained pair outcomes stay missing. Deferred track ROI/proportion settings remain documented in the configuration but are not used in the current run.

## Version control

Git is installed on this computer and works in PowerShell. Git records local file history; GitHub hosts remote repositories; Git Bash is an optional terminal interface.

Source code and local data are managed separately. The local Git workflow connects editing, execution, checks and commits before publishing source changes. See the Git guide for commands.
