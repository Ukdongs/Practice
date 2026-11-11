"""Offline, stdlib-only historical trajectory QA. Never an on-road alert input."""
import argparse
import collections
from contextlib import closing
import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile

FT = 0.3048
REQUIRED = ('location', 'vehicle_id', 'global_time', 'local_x', 'local_y',
            'v_length', 'v_width', 'v_vel', 'v_acc')
POLICY = {'cadence_ms': 100, 'speed_range_mps': [0, 70],
          'acceleration_abs_limit_mps2': 15, 'length_range_m': [0.5, 30],
          'width_range_m': [0.3, 5], 'residual_limit_mps': 5,
          'teleport_step_m': 10, 'quarantine_examples_limit': 20}


def analyze(path):
    """Stream rows; exact uniqueness and last-observation state live on disk.

    Missing-record counts infer internal 100 ms gaps only, never track endpoints.
    Residual = |observed displacement / dt - mean reported endpoint speed|.
    """
    path = Path(path)
    counts = collections.Counter()
    histogram = dict.fromkeys(('0_to_1', '1_to_3', '3_to_5', 'over_5'), 0)
    examples = []
    residual_sum = residual_max = 0.0
    tmin = tmax = None
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(65536), b''):
            digest.update(chunk)

    def flag(reason, line, key=None, time=None):
        counts[reason] += 1
        if len(examples) < 20:
            examples.append(dict(reason=reason, csv_line=line, track=key, time_ms=time))

    with tempfile.TemporaryDirectory(prefix='ngsim_qa_') as temp:
        with closing(sqlite3.connect(str(Path(temp) / 'state.sqlite'))) as db:
            db.execute('PRAGMA cache_size=-2048')
            db.execute('CREATE TABLE seen (loc TEXT, id INTEGER, t INTEGER, PRIMARY KEY(loc,id,t)) WITHOUT ROWID')
            db.execute('CREATE TABLE tracks (loc TEXT, id INTEGER, t INTEGER, x REAL, y REAL, v REAL, PRIMARY KEY(loc,id)) WITHOUT ROWID')
            with path.open(newline='', encoding='utf-8-sig') as source:
                reader = csv.DictReader(source)
                headers = reader.fieldnames or []
                missing = sorted(set(REQUIRED) - set(headers))
                if missing or len(headers) != len(set(headers)):
                    raise ValueError('Invalid headers: missing=' + repr(missing) + '; duplicate headers disallowed')
                for line, row in enumerate(reader, 2):
                    counts['rows'] += 1
                    if None in row or any(row.get(h) is None for h in headers):
                        flag('malformed_rows', line)
                    try:
                        loc = row['location'].strip()
                        vid = int(row['vehicle_id'])
                        t = int(row['global_time'])
                        if not loc or not 0 < vid < 2**63 or not 0 <= t < 2**63:
                            raise ValueError()
                    except (ValueError, TypeError, AttributeError):
                        flag('invalid_identity_or_time', line)
                        continue
                    key = [loc, vid]
                    tmin = t if tmin is None else min(tmin, t)
                    tmax = t if tmax is None else max(tmax, t)
                    duplicate = db.execute('INSERT OR IGNORE INTO seen VALUES (?,?,?)', (loc, vid, t)).rowcount == 0
                    if duplicate:
                        flag('duplicate_vehicle_time', line, key, t)
                    values = {}
                    for name in REQUIRED[3:]:
                        try:
                            value = float(row[name]) * FT
                            if not math.isfinite(value):
                                raise ValueError()
                            values[name] = value
                        except (ValueError, TypeError):
                            flag('invalid_' + name, line, key, t)
                            values[name] = None
                    length, width = values['v_length'], values['v_width']
                    if length is None or width is None or not (0.5 <= length <= 30 and 0.3 <= width <= 5):
                        flag('bad_dimensions', line, key, t)
                    v, acc = values['v_vel'], values['v_acc']
                    if v is not None and not 0 <= v <= 70:
                        flag('implausible_speed', line, key, t)
                    if acc is not None and abs(acc) > 15:
                        flag('implausible_acceleration', line, key, t)
                    x, y = values['local_x'], values['local_y']
                    prev = db.execute('SELECT t,x,y,v FROM tracks WHERE loc=? AND id=?', (loc, vid)).fetchone()
                    if prev:
                        dt = t - prev[0]
                        if dt <= 0:
                            flag('nonmonotonic_vehicle_time', line, key, t)
                        elif dt > 100:
                            flag('internal_time_gaps', line, key, t)
                            if dt % 100 == 0:
                                counts['missing_records_inferred'] += dt // 100 - 1
                        if dt > 0 and dt % 100:
                            flag('off_cadence_intervals', line, key, t)
                        if dt == 100 and not duplicate and all(z is not None for z in (x, y, v, prev[1], prev[2], prev[3])):
                            distance = math.hypot(x - prev[1], y - prev[2])
                            residual = abs(distance * 10 - (v + prev[3]) / 2)
                            counts['compared_intervals'] += 1
                            residual_sum += residual
                            residual_max = max(residual_max, residual)
                            bucket = '0_to_1' if residual <= 1 else '1_to_3' if residual <= 3 else '3_to_5' if residual <= 5 else 'over_5'
                            histogram[bucket] += 1
                            if residual > 5:
                                flag('speed_position_inconsistency', line, key, t)
                            if distance > 10:
                                flag('teleport_or_id_mismatch_candidate', line, key, t)
                    # Keep the high-water timestamp. Invalid coordinates break comparisons.
                    if prev is None or t > prev[0]:
                        db.execute('INSERT OR REPLACE INTO tracks VALUES (?,?,?,?,?,?)', (loc, vid, t, x, y, v))
            vehicles = db.execute('SELECT count(*) FROM tracks').fetchone()[0]
    return {
        'schema_version': 1, 'source': {'file_name': path.name, 'sha256': digest.hexdigest()},
        'scope': 'QA of publicly recorded historical trajectories; not a train/test split or predictive accuracy certification. MUST NOT cause on-road alerts. No real-world safety claim.',
        'units': {'input': 'feet, feet/s, feet/s^2, milliseconds', 'output': 'meters, m/s, m/s^2, milliseconds', 'feet_to_meters': FT},
        'coordinate_semantics': {'local_x_local_y': 'vehicle reference point, NOT validated center; source reference-point convention requires separate verification', 'axes': 'site-dependent; displacement magnitude avoids assuming axis sign or direction', 'heading_validated': False, 'center_validated': False},
        'collision_check': {'status': 'not evaluated', 'overlap_count': None, 'reason': 'Heading geometry and reference-point-to-center semantics are unvalidated. No oriented-rectangle pair comparison is justified.'},
        'row_count': counts['rows'], 'unique_vehicles_by_location_and_id': vehicles,
        'time_span_ms': {'start': tmin, 'end': tmax, 'duration': None if tmin is None else tmax - tmin},
        'counts': {name: counts[name] for name in sorted(set(counts) | {'duplicate_vehicle_time', 'nonmonotonic_vehicle_time', 'bad_dimensions', 'missing_records_inferred', 'speed_position_inconsistency', 'teleport_or_id_mismatch_candidate'})},
        'missing_records_assessment': {'status': 'not evaluated' if counts['nonmonotonic_vehicle_time'] or counts['off_cadence_intervals'] or counts['invalid_identity_or_time'] else 'internal gaps inferred', 'count': None if counts['nonmonotonic_vehicle_time'] or counts['off_cadence_intervals'] or counts['invalid_identity_or_time'] else counts['missing_records_inferred'], 'caveat': 'Gap counter is an arrival-order candidate count only; unordered input can fill apparent gaps later. Endpoints and invalid-coordinate records are not inferred missing.'},
        'speed_position_residual_mps': {'definition': 'absolute displacement-speed minus mean endpoint reported speed, only adjacent 100 ms observations', 'count': counts['compared_intervals'], 'mean': residual_sum / counts['compared_intervals'] if counts['compared_intervals'] else None, 'max': residual_max if counts['compared_intervals'] else None, 'histogram': histogram},
        'recommended_quarantine': {'counts_by_reason': {k: v for k, v in sorted(counts.items()) if k not in ('rows', 'compared_intervals', 'missing_records_inferred')}, 'examples': examples, 'examples_truncated': sum(v for k, v in counts.items() if k not in ('rows', 'compared_intervals', 'missing_records_inferred')) > len(examples), 'interpretation': 'Review flagged records and adjacent intervals; candidates may reflect annotation errors, not proven physical events.'},
        'thresholds': POLICY, 'provenance_review': 'separate review required; local file hash is not provenance verification', 'license_review': 'separate review required; no redistribution authorization inferred'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--output', type=Path, default=Path('artifacts/data_quality/report.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if not output.is_relative_to(root / 'artifacts'):
        parser.error('--output must be inside this repository artifacts directory')
    try:
        report = analyze(args.csv)
    except (ValueError, OSError, csv.Error) as exc:
        parser.exit(2, 'QA input error: ' + str(exc) + '\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(output), 'rows': report['row_count'], 'counts': report['counts']}))


if __name__ == '__main__':
    main()
