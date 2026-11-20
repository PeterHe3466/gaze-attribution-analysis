"""Single entry point: edit the paths below, then run python main.py."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import shutil
import traceback
from uuid import uuid4

from gaze_pipeline.common import require, write_csv, write_json, sha256
from gaze_pipeline.configuration import load_config
from gaze_pipeline.provenance import git_state, environment, code_manifest, verify_manifest, utc_now

PROJECT_ROOT = Path(__file__).resolve().parent

# ===== Edit input, order-reference and output paths here =====
INPUT_DIR = Path(r"C:\Users\Peter\Documents\Syncthing Folder\Peter's Folder\KU course\ReproducibleQuantitativeDataAnalysis-2026\Demo Gaze attribution\data_pre")
ORDER_FILE = INPUT_DIR / 'Gaze-Order.xlsx'
OUTPUT_DIR = Path(r"C:\Users\Peter\Documents\Syncthing Folder\Peter's Folder\KU course\ReproducibleQuantitativeDataAnalysis-2026\Demo Gaze attribution\Analysis output")
# Analysis rules and their descriptions are in config.json beside this file.

SUPPORTED_ANALYSES = {'looking_time', 'pair_looking_time'}


def publish_primary_files(snapshot, output_root):
    """Publish the latest successful CSV/audit; retain their complete run copy."""
    prepared = []
    for name in ['analysis_ready.csv', 'audit.md']:
        temporary = output_root/f'.{name}.{snapshot.name}.tmp'
        shutil.copyfile(snapshot/name, temporary)
        prepared.append((temporary, output_root/name))
    for temporary, target in prepared:
        temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=PROJECT_ROOT/'config.json')
    parser.add_argument('--check-config', action='store_true', help='Validate configuration and print resolved paths without processing data')
    parser.add_argument('--reference-root', type=Path, help='Optional historical Codex directory for refactor regression checks; not a runtime dependency')
    args = parser.parse_args()
    paths = dict(data_root=INPUT_DIR, order_file=ORDER_FILE, output_root=OUTPUT_DIR)
    original, config = load_config(args.config.resolve(), PROJECT_ROOT, SUPPORTED_ANALYSES, paths=paths)
    if args.check_config:
        print(json.dumps(config, indent=2))
        return 0
    # Load scientific dependencies only when running the extraction.
    from gaze_pipeline.inputs import discover_inputs
    import pandas as pd
    from gaze_pipeline.looking_time import extract_looking_time
    from gaze_pipeline.pair_looking_time import extract_pair_looking_time, METADATA
    from gaze_pipeline.verification import verify_results, verify_reference, verify_pair_results
    from gaze_pipeline.audit import write_audit

    root = Path(config['paths']['output_root'])
    root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8]
    output = root/'details'/run_id
    output.mkdir(parents=True, exist_ok=False)
    requested = config['analyses']
    executed = ['looking_time']
    if 'pair_looking_time' in requested:
        executed.append('pair_looking_time')
    start_code = code_manifest(PROJECT_ROOT, root)
    record = dict(run_id=run_id, status='running', started_utc=utc_now(), git=git_state(PROJECT_ROOT),
                  invocation=sys.argv, environment=environment(), requested_analyses=requested, executed_analyses=executed)
    write_json(output/'run_record.json', record)
    write_json(output/'config_requested.json', original)
    write_json(output/'config_resolved.json', config)
    write_json(output/'code_manifest.json', start_code)
    try:
        print('Discovering and validating input files...', flush=True)
        people, inventory, manifests = discover_inputs(config)
        manifests.append({'role': 'configuration', 'path': str(args.config.resolve()), 'bytes': args.config.stat().st_size, 'sha256': sha256(args.config)})
        write_csv(people, output/'participant_order.csv')
        write_csv(inventory, output/'source_inventory.csv')
        write_json(output/'input_manifest.json', manifests)
        print(f'Extracting looking time: {len(people)} participants...', flush=True)
        trials, looking, _ = extract_looking_time(inventory, config['rules'], output)
        pair_people = None
        if 'pair_looking_time' in executed:
            print('Exporting separate Pair 1 and Pair 2 looking times...', flush=True)
            pair_people = extract_pair_looking_time(trials, looking, config['rules'], output)
        master = looking.copy()
        pair_columns = []
        if pair_people is not None:
            pair_columns = [c for c in pair_people if c not in METADATA]
            master = master.merge(pair_people[['participant_id']+pair_columns], on='participant_id', validate='one_to_one')
        write_csv(master, output/'analysis_ready.csv')
        readback = pd.read_csv(output/'analysis_ready.csv')
        require(readback.shape == master.shape and readback.participant_id.is_unique, 'Final CSV readback failed')
        pd.testing.assert_frame_equal(readback, master, check_dtype=False, check_exact=False, atol=1e-9, rtol=0)
        dictionary = [{'column': c, 'dtype': str(master[c].dtype), 'source': 'pair_looking_time' if c in pair_columns else 'looking_time_or_metadata'} for c in master]
        write_json(output/'column_dictionary.json', dictionary)
        checks = verify_results(trials, looking)
        if pair_people is not None:
            checks['pair_looking_time'] = verify_pair_results(trials, looking, pair_people)
        if args.reference_root:
            checks['historical_regression'] = verify_reference(args.reference_root.resolve(), trials, looking)
        verify_manifest(manifests)
        require(start_code == code_manifest(PROJECT_ROOT, root), 'Source code or configuration changed during run')
        checks['all_inputs_unchanged'] = True
        checks['all_code_unchanged'] = True
        write_json(output/'verification.json', checks)
        write_audit(trials, looking, {}, config, record, checks, output)
        record.update(status='success', finished_utc=utc_now(), verification=checks,
                      outputs=[{'path': p.name, 'sha256': sha256(p)} for p in sorted(output.iterdir()) if p.is_file() and p.name != 'run_record.json'])
        write_json(output/'run_record.json', record)
        publish_primary_files(output, root)
        print(f'SUCCESS: {len(master)} participants; {len(master.columns)} columns\n'
              f'CSV: {root / "analysis_ready.csv"}\nAudit: {root / "audit.md"}\nDetails: {output}', flush=True)
        return 0
    except Exception as error:
        record.update(status='failed', finished_utc=utc_now(), error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        write_json(output/'run_record.json', record)
        print(f'FAILED: {error}\nRun record: {output / "run_record.json"}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
