"""Seal existing runs, deduplicating only byte-identical registered inputs.

python3 tests/benchmark/archive_results.py seal
python3 tests/benchmark/archive_results.py verify
python3 tests/benchmark/archive_results.py restore A /tmp/new-copy
No participant commands are executed here. Source folders are read only.
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'results'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def inventory(base):
    result = {}
    for p in sorted(base.rglob('*')):
        if p.is_symlink():
            raise ValueError(f'symlink: {p}')
        if p.is_file():
            result[p.relative_to(base).as_posix()] = {'sha256': digest(p), 'bytes': p.stat().st_size}
    return result

def verify():
    assert digest(OUT / 'archive-manifest.json') == (OUT / 'archive-manifest.sha256').read_text().split()[0], 'manifest checksum'
    m = json.loads((OUT / 'archive-manifest.json').read_text())
    for mode, run in m['runs'].items():
        for rel, entry in run['files'].items():
            p = ROOT / entry['repository_reference'] if 'repository_reference' in entry else OUT / mode / rel
            assert p.stat().st_size == entry['bytes'] and digest(p) == entry['sha256'], str(p)
    print('All archived and referenced bytes verified')
    return m

def seal():
    assert not OUT.exists(), 'refuse overwrite'
    registered = json.loads((HERE / 'environments.json').read_text())
    registration = json.loads((HERE / 'registration.json').read_text())
    manifest = {'sealed_at_utc': datetime.now(timezone.utc).isoformat(),
                'timestamp_assurance': 'local clock; no external custody receipt',
                'registered_materials': {}, 'runs': {}}
    for rel, expected in registration['files_sha256'].items():
        actual = digest(HERE / rel)
        manifest['registered_materials'][rel] = {'expected': expected, 'actual': actual, 'matches': expected == actual}
    OUT.mkdir()
    for mode in ('A', 'B'):
        src = Path('/Users/dima/strateg-benchmark-runs') / mode
        before = inventory(src)
        files = {}
        initial = registered['environments'][mode]['files']
        for rel, entry in before.items():
            item = dict(entry)
            original = initial.get(rel)
            if original:
                item['registered_sha256'] = original['sha256']
                item['registered_matches'] = entry['sha256'] == original['sha256']
            ref = ROOT / original['source'] if original else None
            if rel.startswith('case/inputs/') and ref and ref.is_file() and digest(ref) == entry['sha256']:
                item['repository_reference'] = original['source']
            else:
                dest = OUT / mode / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / rel, dest)
            files[rel] = item
        assert before == inventory(src), 'source changed during seal'
        manifest['runs'][mode] = {'source': str(src), 'files': files,
            'missing_registered': sorted(set(initial) - set(before)),
            'source_before_after_equal': True,
            'empty_directories': [str(p.relative_to(src)) for p in src.rglob('*') if p.is_dir() and not any(p.iterdir())]}
    (OUT / 'archive-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'archive-manifest.sha256').write_text(digest(OUT / 'archive-manifest.json') + '  archive-manifest.json\n')
    verify()

if __name__ == '__main__':
    if sys.argv[1] == 'seal':
        seal()
    elif sys.argv[1] == 'verify':
        verify()
    elif sys.argv[1] == 'restore':
        m = verify()
        mode, target = sys.argv[2], Path(sys.argv[3])
        assert not target.exists(), 'refuse overwrite'
        target.mkdir(parents=True)
        for rel, entry in m['runs'][mode]['files'].items():
            src = ROOT / entry['repository_reference'] if 'repository_reference' in entry else OUT / mode / rel
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        for rel in m['runs'][mode]['empty_directories']:
            (target / rel).mkdir(parents=True, exist_ok=True)
        assert inventory(target) == {r: {k: e[k] for k in ('sha256', 'bytes')} for r, e in m['runs'][mode]['files'].items()}
        print(f'Restored {mode}: {target}')
    else:
        raise SystemExit('seal | verify | restore A|B NEW_DIRECTORY')
