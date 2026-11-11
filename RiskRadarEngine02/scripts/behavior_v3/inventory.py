"""Read-only local input inventory; writes only owned results/manifest.json.

Hashes establish reproducibility, not dataset rights or data-quality approval.
"""
import csv
import hashlib
import json
from pathlib import Path


def describe(path, *, csv_counts=False):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            digest.update(chunk)
    result = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}
    if csv_counts:
        with path.open(encoding='utf-8-sig', newline='') as source:
            reader = csv.reader(source)
            result['headers'] = next(reader)
            result['rows'] = sum(1 for _ in reader)
        result['indicator_mapping'] = 'UNKNOWN; no channel inferred from motion'
        result['eligibility'] = 'not assessed; not used for accuracy or fitting'
    return result


def main():
    owned = Path(__file__).resolve().parent
    root = owned.parent.parent
    raw = Path('C:/Users/Public/Documents/RiskRadarOpenDataResearch')
    inputs = [root/'scripts/sim_v2/model.py', root/'scripts/sim_v2/qa.py',
              root/'RiskRadarPleosApp/app/src/main/assets/demo_data_v2.js']
    manifest = {'scope': 'Codex isolated engineering; no network, commit or push',
                'read_only_inputs': [describe(p) for p in inputs],
                'ngsim_inventory_only': [describe(p, csv_counts=True)
                                         for p in sorted(raw.glob('ngsim_contiguous_*_20s.csv'))],
                'outputs': [describe(p) for p in sorted(owned.glob('*.py'))]}
    for p in [owned/'README.md', root/'prism-risk-engine/tests/test_behavior_v3.py',
              root/'docs/BEHAVIOR_V3_IMPLEMENTATION.md', owned/'results/smoke.json',
              owned/'results/pytest.log', owned/'results/pytest.xml']:
        if p.exists():
            manifest['outputs'].append(describe(p))
    destination = owned/'results/manifest.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(destination)


if __name__ == '__main__':
    main()
