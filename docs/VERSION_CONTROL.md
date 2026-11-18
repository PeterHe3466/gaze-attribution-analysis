# Git and GitHub workflow

## Terminology

- **Git** records local file history and is already installed on this computer.
- **GitHub** hosts and shares remote Git repositories.
- **Git Bash** is an optional terminal interface; PowerShell can run the Git commands here.

GitHub's browser interface can upload files and create commits. Local Git connects editing, execution checks and commits. Official references: [Set up Git](https://docs.github.com/en/get-started/git-basics/set-up-git) and [Connecting to GitHub](https://docs.github.com/en/get-started/using-github/connecting-to-github).

## This local repository

The repository is `Demo Gaze attribution/Analysis` and tracks source, configuration, documentation, tests and `uv.lock`. Its history starts with the baseline created during this migration; it does not reconstruct the older scripts' development history.

The input `data_pre` and output `Analysis output` directories are outside the source repository. `.venv/`, `.uv-cache/`, `*.local.json` and similar machine-local files are ignored. Preserving result runs and committing source are separate operations.

Open the repository:

```powershell
Set-Location -LiteralPath "C:\Users\Peter\Documents\Syncthing Folder\Peter's Folder\KU course\ReproducibleQuantitativeDataAnalysis-2026\Demo Gaze attribution\Analysis"
git status
git log --oneline -5
```

## Make an analysis change

1. Create a branch for the change, for example `git switch -c analysis/new-window`.
2. Edit `config.json` or copy it to `new_window.json`. Edit paths at the top of `main.py`. Add a module and update `main.py` when implementing a new outcome.
3. Run tests, then execute the pipeline:

   ```powershell
   uv run --frozen --cache-dir .uv-cache python -m unittest discover -s tests -v
   uv run --frozen --cache-dir .uv-cache python main.py --config new_window.json
   ```

4. Review `audit.md`, the run's `verification.json`, trial exclusions and results. Use `git diff` to review source/configuration changes.
5. Commit the relevant files:

   ```powershell
   git add main.py config.json gaze_pipeline docs tests
   git commit -m "Add alternative measurement-window configuration"
   ```

A commit saves selected files; it does not run the analysis. Runs made with uncommitted changes record `dirty: true` and source hashes. Run again after committing to produce a result associated with a clean commit.

For a new dependency, edit `pyproject.toml`, update the lock with `uv lock --cache-dir .uv-cache`, synchronize the environment and verify. Commit the project file, lock and relevant documentation together. `requirements.txt` lists the current direct dependencies; `uv.lock` defines the complete resolved graph.

## Synchronize with GitHub

This project is published as the private repository [PeterHe3466/gaze-attribution-analysis](https://github.com/PeterHe3466/gaze-attribution-analysis). The local `main` branch tracks `origin/main`, and the repository is already added to GitHub Desktop as `gaze-attribution-analysis`.

For future updates in GitHub Desktop:

1. Select `gaze-attribution-analysis` under Current repository.
2. After editing files locally, review the Changes tab and select the intended files.
3. Enter a short Summary and click **Commit to main** to save the local version.
4. Click **Push origin** to synchronize the new commit with GitHub. If the toolbar shows **Fetch origin** with no outgoing commits, there is nothing waiting to be pushed.

Committing and pushing are separate steps. Future edits are not uploaded automatically merely because this first publication succeeded.

Browser uploads should preserve the reviewed project's source directory structure. The parent `Demo Gaze attribution` directory also contains participant data, older outputs and other analyses; select the intended source files when publishing.

## Archive a result

Retain the complete successful run directory with its source commit and lock file. `run_record.json` includes commit, dirty status, environment versions and output hashes.

To export the committed source snapshot:

```powershell
git archive --format=zip --output=../gaze-pipeline-source.zip HEAD
```

The archive contains committed source files. Local run outputs and external input data are preserved separately. For a citable long-term code archive, a GitHub release can be archived with Zenodo; see [GitHub's DOI guidance](https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content).
