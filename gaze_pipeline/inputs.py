from pathlib import Path
import re

import numpy as np
import pandas as pd

from .common import require, sha256

REQUIRED = ['frame_no', 'frame_time', 'filtered_gaze_pos_x', 'filtered_gaze_pos_y',
            'Screen-Space_pupil', 'stimulus_file', 'trial_label', 'subject_code']


def read_trial(path, participant_number, expected, trial):
    path = Path(path)
    data = pd.read_csv(path)
    require(set(REQUIRED) <= set(data), f'{path.name}: missing columns {set(REQUIRED) - set(data)}')
    for column in REQUIRED[:5] + ['subject_code']:
        data[column] = pd.to_numeric(data[column], errors='raise')
    for column in ['frame_no', 'frame_time']:
        require(np.isfinite(data[column]).all() and data[column].is_unique and data[column].is_monotonic_increasing,
                f'{path.name}: {column} must be finite, unique and increasing')
    require(len(data) > 0, f'{path.name}: empty trial')
    require(data.stimulus_file.dropna().unique().tolist() == [expected], f'{path.name}: stimulus mismatch')
    require(data.trial_label.dropna().unique().tolist() == [f'Gaze_{trial}'], f'{path.name}: trial label mismatch')
    require(set(data.subject_code) == {participant_number}, f'{path.name}: subject code mismatch')
    return data


def discover_inputs(config):
    root = Path(config['paths']['data_root'])
    order_path = Path(config['paths']['order_file'])
    require(root.is_dir(), f'Data directory not found: {root}')
    require(order_path.is_file(), f'Order reference not found: {order_path}')
    order_digest = sha256(order_path)
    orders = pd.read_csv(order_path) if order_path.suffix.lower() == '.csv' else pd.read_excel(order_path)
    required_order = ['Order', 'Condition'] + [f'Fami{i}' for i in range(1, 5)] + [f'Test{i}' for i in range(1, 5)]
    require(set(required_order) <= set(orders), 'Order reference lacks required columns')
    require(orders.Order.notna().all() and orders.Order.is_unique, 'Order numbers must be present and unique')
    manifests = [{'role': 'order_reference', 'path': str(order_path), 'bytes': order_path.stat().st_size, 'sha256': order_digest}]
    people, inventory = [], []
    requested = set(config['selection']['participants'])
    for age in sorted(set(config['selection']['ages_months'])):
        age_root = root / f'{age}mo_data_pre'
        require(age_root.is_dir(), f'Age directory missing: {age_root}')
        for folder in sorted(age_root.iterdir()):
            match = re.fullmatch(r'(P\d+)_preprocessed', folder.name)
            if not folder.is_dir() or not match:
                continue
            pid = match[1]
            ident = f'{age}mo_{pid}'
            if requested and ident not in requested:
                continue
            observed, files = {}, {}
            for path in sorted(folder.glob('*.csv')):
                token = re.search(r'_(Fami[1-4]|Gaze_Test[1-4])$', path.stem)
                if not token:
                    continue
                trial = token[1].removeprefix('Gaze_')
                require(trial not in files, f'{ident}: duplicate {trial}')
                digest = sha256(path)
                meta = pd.read_csv(path, usecols=['stimulus_file'])
                values = meta.stimulus_file.dropna().unique().tolist()
                require(len(values) == 1, f'{ident} {trial}: stimulus must be unambiguous')
                observed[trial], files[trial] = values[0], path
                manifests.append({'role': 'postprocessed_trial', 'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest})
            require(any(t.startswith('Test') for t in observed), f'{ident}: no Test trials found')
            candidates = []
            for _, ref in orders.iterrows():
                if all(observed[t] == f'{ref.Condition}-{ref[t]}.mp4' for t in observed if t.startswith('Test')):
                    candidates.append(ref)
            require(len(candidates) == 1, f'{ident}: order matched {len(candidates)} reference rows')
            ref = candidates[0]
            require(ref.Condition in config['rules']['condition_labels'], f'Unmapped condition: {ref.Condition}')
            for i in range(1, 5):
                require(observed.get(f'Fami{i}') == f'Fami_{ref.Condition.upper()}_{ref[f"Fami{i}"]}.mp4', f'{ident}: Fami{i} order mismatch or missing file')
            person = dict(participant_id=ident, age_months=age, participant=pid, condition=ref.Condition,
                          order_number=int(ref.Order), test_sequence=''.join(ref[f'Test{i}'].split('-')[-1][0] for i in range(1, 5)))
            for i in range(1, 5):
                trial = f'Test{i}'
                expected = f'{ref.Condition}-{ref[trial]}.mp4'
                path = files.get(trial)
                inventory.append({**person, 'trial': trial, 'trial_number': i, 'pair_number': (i+1)//2,
                                  'expected_stimulus': expected, 'source': str(path) if path else None,
                                  'side': ref[trial].split('-')[0], 'event': ref[trial].split('-')[1]})
            people.append(person)
    require(bool(people), 'No participants selected')
    found = {p['participant_id'] for p in people}
    require(not requested - found, f'Participant IDs not found in selected ages: {sorted(requested - found)}')
    require(len(found) == len(people), 'Duplicate participant IDs')
    return pd.DataFrame(people), pd.DataFrame(inventory), manifests
