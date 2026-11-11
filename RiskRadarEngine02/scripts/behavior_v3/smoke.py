"""Deterministic offline synthetic replay. Run from repository root with -m.

No real held-out performance claim. Output defaults inside owned directory.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from .intent import IntentEngine, Neighbor, Observation, Parameters
from .evaluation import Event, event_metrics, require_physical_pass


def sidecar(v, timestamp, lane_center, neighbors):
    # SIM world +x right,+y forward, heading measured from +x. Road is straight.
    return Observation(v['id'], timestamp, v['x'], v['y'], v['vx'], v['vy'],
                       yaw_rad=math.pi/2-v['heading_rad'], lane_center_d_m=lane_center,
                       neighbors=tuple(Neighbor(n['id'], timestamp, n['x'], n['y'], n['vx'],
                                                n['vy'], n['length_m'], n['width_m'],
                                                math.pi/2-n['heading_rad'])
                                       for n in neighbors if n['id'] != v['id']))


def run():
    from scripts.sim_v2.model import LANES, SCENES, simulate
    from scripts.sim_v2.qa import collision, rectangle
    reports, alerts, events, ttl_samples = [], [], [], []
    valid_ms = 0
    overlap_tp = overlap_fp = overlap_fn = overlap_tn = 0
    future_tp = future_fp = future_fn = future_tn = 0
    output_counts = {}
    for name in SCENES:
        scene = simulate(name)
        qa = require_physical_pass(scene)
        engine = IntentEngine()
        centers = {v['id']: min(LANES, key=lambda x: abs(x-v['x']))
                   for v in scene['world'][0]['vehicles']}
        previous, crossed, last_alert_direction = {}, set(), {}
        scene_frames = 0
        for frame_index, frame in enumerate(scene['world']):
            t = frame['timestamp_ms']
            for v in frame['vehicles']:
                ident = v['id']
                key = name+'/'+ident
                o = sidecar(v, t, centers[ident], frame['vehicles'])
                result = engine.observe(o, now_ms=t)
                scene_frames += 1
                output_counts[result.motion_intention] = output_counts.get(result.motion_intention, 0)+1
                # Complete 3s prediction horizons, warmup excluded; per-track exposure.
                if 100 <= t <= 7000:
                    valid_ms += 50
                label = result.motion_intention
                direction = label.split('_')[-1] if label.startswith(('PREPARE_', 'CHANGE_')) else None
                if direction and direction != last_alert_direction.get(ident) and 100 <= t <= 7000:
                    alerts.append(Event(key, direction, t))
                    ttl_samples.append({'track_id': key, 'time_ms': t, 'direction': direction,
                                        'estimated_time_to_line_s': result.features['time_to_line_s'][direction]})
                last_alert_direction[ident] = direction
                # Ground truth is actual measured body edge crossing initial lane line,
                # NOT simulator request/accepted events. Labels never reach observe().
                extent = abs(math.cos(o.yaw_rad))*o.width_m/2+abs(math.sin(o.yaw_rad))*o.length_m/2
                offset = o.d_m-centers[ident]
                for d, sign in (('LEFT', -1), ('RIGHT', 1)):
                    edge = sign*offset+extent
                    edge_key = (ident, d)
                    if edge_key not in crossed and previous.get(edge_key, 0) < 1.8 <= edge:
                        crossed.add(edge_key)
                        if t < 100 or t > 7000:
                            raise ValueError('Smoke event is boundary-censored; revise metric cohort explicitly')
                        if 100 <= t <= 7000:
                            events.append(Event(key, d, t))
                    previous[edge_key] = edge
                # Compare current body geometry with independent sim_v2 OBB truth.
                predicted_now = set(result.risk_geometry.get('observed_body_overlap_ids') or [])
                predicted_future = {n['track_id'] for n in result.risk_geometry.get('cv_projected_overlap') or []}
                for n in frame['vehicles']:
                    if n['id'] == ident:
                        continue
                    true_now = collision(rectangle(v), rectangle(n))
                    estimate = n['id'] in predicted_now
                    overlap_tp += int(true_now and estimate)
                    overlap_fp += int(not true_now and estimate)
                    overlap_fn += int(true_now and not estimate)
                    overlap_tn += int(not true_now and not estimate)
                    if 100 <= t <= 7000:
                        future_hit = False
                        # Labels only: measured world states at the SAME horizon samples
                        # as CV hypotheses. Never passed to the inference module.
                        for tick in range(5, 41, 5):
                            truth = {z['id']: z for z in scene['world'][frame_index+tick]['vehicles']}
                            future_hit |= collision(rectangle(truth[ident]), rectangle(truth[n['id']]))
                        candidate = n['id'] in predicted_future
                        future_tp += int(future_hit and candidate)
                        future_fp += int(not future_hit and candidate)
                        future_fn += int(future_hit and not candidate)
                        future_tn += int(not future_hit and not candidate)
        reports.append({'scene': name, 'status': qa['status'], 'physical_samples': qa['samples'],
                        'physical_pair_checks': qa['pair_checks'], 'collisions': len(qa['collisions']),
                        'track_frames': scene_frames})
    metrics = event_metrics(alerts, events, exposure_track_hours=valid_ms/3600000)
    for sample in ttl_samples:
        matches = [e for e in events if e.track_id == sample['track_id']
                   and e.direction == sample['direction']
                   and 0 <= e.timestamp_ms-sample['time_ms'] <= 3000]
        lead = (min(matches, key=lambda e: e.timestamp_ms).timestamp_ms-sample['time_ms'])/1000 if matches else None
        sample['observed_crossing_lead_s'] = lead
        estimate = sample['estimated_time_to_line_s']
        sample['cv_time_to_line_error_s'] = estimate-lead if estimate is not None and lead is not None else None
    return {'status': 'PASS', 'scope': 'synthetic smoke only; no real held-out accuracy',
            'parameters_EXPERIMENTAL': asdict(Parameters()), 'scenes': reports,
            'motion_output_counts': output_counts, 'event_metrics': metrics,
            'alert_time_to_line': ttl_samples,
            'observed_events': [asdict(e) for e in events],
            'metric_cohort': 'episode onsets and events 100..7000ms; alerts followed through 10000ms; fixture boundary-event gate',
            'observed_geometry_vs_independent_physical_truth':
                {'tp': overlap_tp, 'fp': overlap_fp, 'fn': overlap_fn, 'tn': overlap_tn,
                 'limitation': 'collision-free scenes contain no positive physical overlap examples'},
            'cv_risk_zone_vs_future_observed_physical_overlap':
                {'tp': future_tp, 'fp': future_fp, 'fn': future_fn, 'tn': future_tn,
                 'semantics': 'directed pair-horizons, samples .25..2s; not intention accuracy or collision probability'},
            'risk_zone_overlap_definition': 'CV projected OBB overlap is a candidate only; current OBB evaluated separately',
            'real_holdout': {'status': 'BLOCKED', 'reasons': [
                'no verified driver-disjoint labeled lane-relative real dataset supplied',
                'NGSIM 20s QA/rights/lane-map validation and observed event labels not established here',
                'no indicator channel invented; no real calibration performed']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('scripts/behavior_v3/results/smoke.json'))
    args = parser.parse_args()
    owned = Path(__file__).resolve().parent
    if not args.output.resolve().is_relative_to(owned):
        parser.error('Output must remain inside scripts/behavior_v3')
    result = run()  # fail BEFORE writing any success report
    result['source_sha256'] = {str(p.relative_to(owned.parent.parent)).replace('\\', '/'):
                               hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(owned.glob('*.py'))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'output': str(args.output),
                      'event_metrics': result['event_metrics']}, indent=2))


if __name__ == '__main__':
    main()
