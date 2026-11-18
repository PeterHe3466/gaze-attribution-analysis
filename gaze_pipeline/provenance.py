from datetime import datetime, timezone
import importlib.metadata
from pathlib import Path
import platform
import subprocess
import sys

from .common import sha256, require


def git_state(root):
    def run(*args):
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    commit = run('rev-parse', 'HEAD')
    status = run('status', '--porcelain', '--untracked-files=normal')
    return {'commit': commit, 'dirty': bool(status) if status is not None else None, 'status': status}


def environment():
    return dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
                packages={p: importlib.metadata.version(p) for p in ['numpy', 'pandas', 'openpyxl']})


def code_manifest(root, output_root=None):
    selected = []
    for path in sorted(Path(root).rglob('*')):
        relative = path.relative_to(root)
        if output_root is not None and path.resolve().is_relative_to(Path(output_root).resolve()):
            continue
        if not path.is_file() or any(p.startswith('.') or p in {'outputs', '__pycache__', 'data'} for p in relative.parts):
            continue
        if path.suffix in {'.py', '.json', '.toml', '.txt', '.md', '.lock', '.csv'}:
            selected.append({'path': relative.as_posix(), 'sha256': sha256(path)})
    return selected


def verify_manifest(manifest):
    for entry in manifest:
        require(sha256(entry['path']) == entry['sha256'], f'Input changed during run: {entry["path"]}')


def utc_now():
    return datetime.now(timezone.utc).isoformat()
