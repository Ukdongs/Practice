"""Isolated research contract/counterexamples; never modifies v1 engine or V2."""
from dataclasses import replace
import json
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.behavior_v3 import IntentEngine, Neighbor, Observation, Parameters
from scripts.behavior_v3.evaluation import Event, Window, event_metrics, require_physical_pass, validate_holdout, temporal_holdout


def obs(t=0, **kwargs):
    return Observation('target', t, **(dict(d_m=0., s_m=t*.02, vd_mps=0., vs_mps=20.) | kwargs))


def stable(**kwargs):
    engine = IntentEngine()
    engine.observe(obs(**kwargs), now_ms=0)
    return engine, engine.observe(obs(100, **kwargs), now_ms=100)


def test_constant_lane_keep():
    _, r = stable()
    assert r.motion_intention == 'KEEP'
    assert r.features['lateral_acceleration_mps2'] == 0


@pytest.mark.parametrize('direction,velocity', [('LEFT', -.8), ('RIGHT', .8)])
def test_no_signal_rapid_cutin(direction, velocity):
    engine = IntentEngine()
    engine.observe(obs(vd_mps=velocity), now_ms=0)
    r = engine.observe(obs(100, d_m=velocity*.1, vd_mps=velocity), now_ms=100)
    assert r.motion_intention == 'CHANGE_'+direction
    assert r.features['indicator'] == 'UNKNOWN'


@pytest.mark.parametrize('direction', ['LEFT', 'RIGHT'])
def test_signal_without_change_only_prepare(direction):
    _, r = stable(indicator=direction, indicator_provenance='OBSERVED')
    assert r.motion_intention == 'PREPARE_'+direction
    assert r.risk_geometry['cv_projected_overlap'] == []


def test_tentative_abort_sequence():
    e = IntentEngine()
    e.observe(obs(d_m=-.2, vd_mps=-.4), now_ms=0)
    r = e.observe(obs(100, d_m=-.24, vd_mps=-.4), now_ms=100)
    assert r.motion_intention == 'PREPARE_LEFT'
    r = e.observe(obs(200, d_m=-.24, vd_mps=.4), now_ms=200)
    assert r.motion_intention == 'ABORT_LEFT'


@pytest.mark.parametrize('signal,provenance', [('BOTH', 'OBSERVED'), ('LEFT', 'UNKNOWN'),
                                              ('UNKNOWN', 'OBSERVED'), ('OFF', 'UNKNOWN'),
                                              ('LEFT', 'INFERRED')])
def test_unavailable_or_both_blinkers_unknown(signal, provenance):
    _, r = stable(indicator=signal, indicator_provenance=provenance)
    assert r.features['indicator'] == 'UNKNOWN'
    assert r.motion_intention == 'KEEP'


def test_observed_off_is_not_missing():
    _, r = stable(indicator='OFF', indicator_provenance='OBSERVED')
    assert r.features['indicator_observed']
    assert r.features['indicator'] == 'OFF'


def test_synthetic_signal_remains_marked():
    _, r = stable(indicator='LEFT', indicator_provenance='SYNTHETIC')
    assert not r.features['indicator_observed']
    assert 'synthetic_indicator_research_only' in r.uncertainty


def test_stale_frame_does_not_poison_history():
    e, _ = stable()
    assert e.observe(obs(150), now_ms=500).motion_intention == 'UNKNOWN'
    r = e.observe(obs(500), now_ms=500)
    assert r.features['track_age_s'] == .5


def test_future_frame_rejected():
    assert IntentEngine().observe(obs(100), now_ms=0).motion_intention == 'UNKNOWN'


def test_duplicate_and_delayed_out_of_order():
    e, _ = stable()
    for t in (100, 50):
        assert 'duplicate_or_out_of_order' in e.observe(obs(t), now_ms=100).reasons


def test_reception_clock_monotonic():
    e, _ = stable()
    assert 'nonmonotonic_clock' in e.observe(obs(50), now_ms=50).reasons


def test_expiry_resets_track_age():
    e, _ = stable()
    r = e.observe(obs(1200), now_ms=1200)
    assert r.motion_intention == 'UNKNOWN'
    assert r.features['track_age_s'] == 0


def test_missing_observation_unknown():
    r = IntentEngine().observe(None, now_ms=0, missing_track_id='missing')
    assert r.track_id == 'missing' and r.motion_intention == 'UNKNOWN'
    assert r.risk_geometry['observed_body_overlap_ids'] is None


def test_mistracked_id_discontinuity():
    e, _ = stable()
    r = e.observe(obs(200, d_m=15), now_ms=200)
    assert r.reasons == ('track_discontinuity',)


def test_identity_epoch_reset_even_without_jump():
    e, _ = stable()
    r = e.observe(obs(200, identity_epoch='new'), now_ms=200)
    assert r.reasons == ('identity_or_lane_reference_reset',)


def test_new_track_does_not_inherit_old_state():
    e, _ = stable(indicator='LEFT', indicator_provenance='OBSERVED')
    r = e.observe(replace(obs(200), track_id='other'), now_ms=200)
    assert r.motion_intention == 'UNKNOWN' and r.features['track_age_s'] == 0


def test_road_curvature_uses_road_relative_yaw_and_motion():
    # World heading may rotate; adapter supplies road-relative yaw=0, d velocity=0.
    _, r = stable(yaw_rad=0.)
    assert r.motion_intention == 'KEEP'
    _, uncertain = stable(lane_geometry_reliable=False)
    assert uncertain.motion_intention == 'UNKNOWN'


def test_reference_change_cannot_look_like_lane_change():
    e, _ = stable()
    r = e.observe(obs(200, lane_center_d_m=3.6), now_ms=200)
    assert r.motion_intention == 'UNKNOWN'


def test_fast_rear_approach_geometry_without_lane_intention():
    n = Neighbor('rear', 100, 0, -18, 0, 35)
    e = IntentEngine()
    e.observe(obs(), now_ms=0)
    r = e.observe(obs(100, neighbors=(n,)), now_ms=100)
    assert r.motion_intention == 'KEEP'
    assert r.risk_geometry['observed_body_overlap_ids'] == []
    assert r.risk_geometry['cv_projected_overlap'][0]['track_id'] == 'rear'
    assert r.risk_geometry['neighbor_gaps'][0]['position'] == 'REAR'
    assert r.risk_geometry['neighbor_gaps'][0]['closing_mps'] == 15


def test_adjacent_slow_front_not_current_collision():
    e, _ = stable()
    r = e.observe(obs(200, neighbors=(Neighbor('slow', 200, 3.6, 20, 0, 5),)), now_ms=200)
    g = r.risk_geometry['neighbor_gaps'][0]
    assert g['side'] == 'RIGHT' and g['closing_mps'] == 15
    assert r.risk_geometry['observed_body_overlap_ids'] == []
    assert r.risk_geometry['cv_projected_overlap'] == []


def test_simultaneous_merge_projected_overlap_not_actual_collision():
    e = IntentEngine()
    e.observe(obs(d_m=-1.5, vd_mps=.8), now_ms=0)
    n = Neighbor('other', 100, 1.5, 2, -.8, 20)
    r = e.observe(obs(100, d_m=-1.42, vd_mps=.8, neighbors=(n,)), now_ms=100)
    assert r.motion_intention == 'CHANGE_RIGHT'
    assert r.risk_geometry['observed_body_overlap_ids'] == []
    assert r.risk_geometry['cv_projected_overlap']


def test_observed_physical_overlap_is_exposed():
    _, r = stable(neighbors=(Neighbor('hit', 100, .5, 2, 0, 20),))
    assert r.risk_geometry['observed_body_overlap_ids'] == ['hit']


def test_unsynchronized_neighbor_is_omitted():
    _, r = stable(neighbors=(Neighbor('stale', 0, 0, 0, 0, 20),))
    assert r.risk_geometry['observed_body_overlap_ids'] == []
    assert 'invalid_or_unsynchronized_neighbors_omitted' in r.uncertainty


def test_duplicate_neighbor_identity_is_not_trusted():
    n = Neighbor('same', 100, 0, 0, 0, 20)
    _, r = stable(neighbors=(n, n))
    assert r.risk_geometry['neighbor_gaps'] == []


def test_braking_from_past_speed_difference():
    e, _ = stable()
    r = e.observe(obs(200, vs_mps=19.7, front_event='BRAKING'), now_ms=200)
    assert r.motion_intention == 'BRAKE'
    assert r.features['longitudinal_acceleration_mps2'] == pytest.approx(-3)
    assert r.features['front_event'] == 'BRAKING'


def test_front_event_alone_cannot_fabricate_braking():
    _, r = stable(front_event='BRAKING')
    assert r.motion_intention == 'KEEP'


def test_yield_requires_braking_and_adjacent_interaction():
    e, _ = stable(indicator='LEFT', indicator_provenance='OBSERVED')
    n = Neighbor('priority', 200, -3.6, 12, 0, 10)
    r = e.observe(obs(200, vs_mps=19.7, indicator='LEFT', indicator_provenance='OBSERVED',
                      neighbors=(n,)), now_ms=200)
    assert r.motion_intention == 'YIELD'


def test_time_to_line_uses_leading_body_edge():
    e = IntentEngine()
    e.observe(obs(vd_mps=.5), now_ms=0)
    r = e.observe(obs(100, d_m=.05, vd_mps=.5), now_ms=100)
    assert r.features['time_to_line_s']['RIGHT'] == pytest.approx(1.6)
    assert r.features['time_to_line_s']['LEFT'] is None


def test_yaw_changes_body_extent_but_not_intent_alone():
    _, r = stable(yaw_rad=.15)
    assert r.motion_intention == 'KEEP'
    assert r.features['body_distance_to_line_m']['RIGHT'] < .85


def test_lateral_acceleration_is_backward_difference():
    e, _ = stable()
    r = e.observe(obs(200, d_m=.02, vd_mps=.4), now_ms=200)
    assert r.features['lateral_acceleration_mps2'] == pytest.approx(4.)


@pytest.mark.parametrize('kwargs', [dict(d_m=float('nan')), dict(vd_mps=float('inf')),
                                   dict(vs_mps=100), dict(width_m=-1), dict(lane_width_m=0),
                                   dict(reliable=False), dict(lane_geometry_reliable=False)])
def test_invalid_data_unknown(kwargs):
    assert IntentEngine().observe(obs(**kwargs), now_ms=0).motion_intention == 'UNKNOWN'


def test_smooth_threshold_has_no_score_jump():
    def score(v):
        e = IntentEngine()
        e.observe(obs(vd_mps=v), now_ms=0)
        return e.observe(obs(100, d_m=v*.1, vd_mps=v), now_ms=100).scores['RIGHT']
    assert abs(score(.300001)-score(.299999)) < .0001


def test_prefix_invariance_no_future_truth_interface():
    seq = [obs(t, d_m=t*.0004, vd_mps=.4) for t in (0, 100, 200, 300)]
    a, b = IntentEngine(), IntentEngine()
    prefix = [a.observe(o, now_ms=o.timestamp_ms).to_dict() for o in seq[:3]]
    full = [b.observe(o, now_ms=o.timestamp_ms).to_dict() for o in seq]
    assert prefix == full[:3]
    assert 'future' not in Observation.__dataclass_fields__


def test_json_contract_has_no_false_confidence_or_probability():
    _, r = stable()
    text = json.dumps(r.to_dict(), allow_nan=False)
    assert r.schema_version == 'BehaviorIntentFrame v0'
    assert r.score_semantics == 'heuristic score not calibrated'
    assert 'confidence' not in r.to_dict() and 'probability' not in r.to_dict()
    assert json.loads(text)['research_only']


def test_short_dt_unknown():
    e = IntentEngine()
    e.observe(obs(), now_ms=0)
    assert 'sampling_interval_too_short' in e.observe(obs(1), now_ms=1).reasons


def test_bad_parameters_rejected():
    with pytest.raises(ValueError):
        IntentEngine(Parameters(projection_step_s=0))


def test_implausible_acceleration_unknown():
    e, _ = stable()
    assert e.observe(obs(200, vd_mps=5), now_ms=200).reasons == ('implausible_acceleration',)


def test_negative_timestamp_unknown():
    assert IntentEngine().observe(obs(-1), now_ms=0).motion_intention == 'UNKNOWN'


def test_nonfinite_parameters_rejected():
    with pytest.raises(ValueError):
        IntentEngine(Parameters(horizon_s=float('inf')))


def test_event_metrics_one_to_one_precision_recall_and_lead():
    a = [Event('a', 'LEFT', 1000), Event('a', 'LEFT', 1500), Event('b', 'RIGHT', 2000)]
    e = [Event('a', 'LEFT', 2500), Event('c', 'LEFT', 3000)]
    r = event_metrics(a, e, exposure_track_hours=.5)
    assert r['precision'] == pytest.approx(1/3)
    assert r['recall'] == .5 and r['false_alerts_per_track_hour'] == 4
    assert r['lead_time_s'] == [1.5]


def test_late_or_wrong_direction_alert_not_matched():
    r = event_metrics([Event('a', 'RIGHT', 900), Event('a', 'LEFT', 1100)],
                      [Event('a', 'LEFT', 1000)], exposure_track_hours=1)
    assert r['missed_events'] == 1 and r['false_alert_episodes'] == 2


def test_empty_event_metrics_does_not_invent_performance():
    r = event_metrics([], [], exposure_track_hours=1)
    assert r['precision'] is None and r['recall'] is None
    with pytest.raises(ValueError):
        event_metrics([], [], exposure_track_hours=0)


def windows():
    return [Window('a', 'r1', 'd1', 0, 1000, 'train'),
            Window('b', 'r2', 'd2', 2000, 3000, 'validation'),
            Window('c', 'r3', 'd3', 4000, 5000, 'test')]


def test_scene_driver_temporal_holdout_pass():
    assert validate_holdout(windows(), embargo_ms=500)['status'] == 'PASS'


def test_split_assignment_before_any_fitting():
    w = [replace(x, split='unused') for x in windows()]
    result = temporal_holdout(w, train_end_ms=1000, validation_end_ms=3000, embargo_ms=500)
    assert [x.split for x in result] == ['train', 'validation', 'test']


def test_split_straddling_window_rejected():
    with pytest.raises(ValueError, match='straddles'):
        temporal_holdout([replace(windows()[0], end_ms=1500)], train_end_ms=1000, validation_end_ms=3000)


@pytest.mark.parametrize('field,value', [('site', 'a'), ('driver', 'd1'), ('driver', 'UNKNOWN'),
                                        ('start_ms', 500)])
def test_holdout_leakage_rejected(field, value):
    w = windows()
    w[1] = replace(w[1], **{field: value})
    with pytest.raises(ValueError):
        validate_holdout(w)


def test_overlapping_same_recording_windows_rejected():
    a = windows()[0]
    with pytest.raises(ValueError):
        validate_holdout([a, replace(a, start_ms=900, end_ms=2000)])


@pytest.mark.parametrize('name', ['lane_change', 'yield_merge', 'shockwave', 'dense'])
def test_unmodified_sim_v2_physical_gate(name):
    from scripts.sim_v2.model import simulate
    assert not require_physical_pass(simulate(name))['collisions']


@pytest.mark.parametrize('index', [0, 50, 100, 200])
def test_every_injected_sim_collision_sample_fails(index):
    from scripts.sim_v2.model import simulate
    s = simulate('shockwave')
    vs = s['world'][index]['vehicles']
    vs[1].update(x=vs[0]['x'], y=vs[0]['y'])
    with pytest.raises(ValueError, match='Physical QA FAIL'):
        require_physical_pass(s)


def test_prediction_overlap_does_not_fail_physical_gate():
    from scripts.sim_v2.model import simulate
    s = simulate('shockwave')
    s['predictions'] = {'overlap': True}  # not physical world truth
    assert require_physical_pass(s)['status'] == 'PASS'


def test_runtime_imports_only_stdlib_and_local_contract():
    import ast
    tree = ast.parse((ROOT/'scripts/behavior_v3/intent.py').read_text(encoding='utf-8'))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert set(imports) <= {'__future__', 'dataclasses', 'math'}
