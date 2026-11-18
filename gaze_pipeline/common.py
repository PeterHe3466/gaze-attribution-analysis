from pathlib import Path
import hashlib
import json

import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_csv(table, path):
    table.to_csv(path, index=False, encoding='utf-8-sig', float_format='%.12f', na_rep='')


def log10_positive(value):
    return float(np.log10(value)) if np.isfinite(value) and value > 0 else np.nan


def retained_prefix(complete, pair_numbers):
    kept = []
    for pair in pair_numbers:
        if pair not in complete:
            break
        kept.append(pair)
    return kept
