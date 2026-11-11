import copy
import math
import pytest
from scripts.sim_v2.model import Car, SCENES, simulate, safe_change, to_local
from scripts.sim_v2.qa import audit, rectangle, collision, clearance
from scripts.sim_v2.generate import export_scene

@pytest.mark.parametrize('name',SCENES)
def test_demo_physical_gate(name):
    result=audit(simulate(name))
    assert result['status']=='PASS',result
    assert not result['collisions']

def test_fast_rear_blocks_future_gap():
    c=Car('ego',0,0,20,target=3.6)
    assert not safe_change(c,[c,Car('rear',3.6,-45,32)],3.6)
    assert safe_change(c,[c,Car('rear',3.6,-100,20)],3.6)

def test_slow_front_blocks_future_gap():
    c=Car('ego',0,0,25,target=3.6)
    assert not safe_change(c,[c,Car('front',3.6,50,10)],3.6)

def test_lane_change_delayed_then_completed():
    s=simulate('lane_change')
    assert [e['event'] for e in s['events']]==['delayed_unsafe_front_or_rear','accepted']
    assert next(v for v in s['world'][-1]['vehicles'] if v['id']=='changer')['x']==-3.6

def test_merge_yields_and_completes():
    s=simulate('yield_merge')
    assert s['events'][0]['event']=='delayed_unsafe_front_or_rear'
    assert any(e['event']=='accepted' for e in s['events'])
    merger=lambda frame:next(v for v in frame['vehicles'] if v['id']=='merger')
    assert min(merger(f)['vy'] for f in s['world'])<19
    assert merger(s['world'][-1])['x']==0

def test_braking_propagates_upstream():
    s=simulate('shockwave')
    first={ident:next(f['timestamp_ms'] for f in s['world'] if next(v for v in f['vehicles'] if v['id']==ident)['ay']<-.5)
        for ident in ('ego','response','brake_lead')}
    assert first['brake_lead']<first['response']<first['ego']
    assert next(v for v in s['world'][-1]['vehicles'] if v['id']=='ego')['vy']<18

def test_stop_queue_and_cut_in():
    cars=[Car('ego',0,0,12,15),Car('stopped',0,60,0,.1),Car('cutin',3.6,30,12,15,target=0)]
    s=simulate('test',cars)
    assert audit(s)['status']=='PASS'
    assert next(v for v in s['world'][-1]['vehicles'] if v['id']=='ego')['vy']<2

def test_rotated_obb_and_clearance():
    a=Car('a',0,0,0).state(); b=Car('b',3.6,0,0).state()
    assert not collision(rectangle(a),rectangle(b))
    assert clearance(rectangle(a),rectangle(b))==pytest.approx(1.7)
    b.update(x=1.,heading_rad=.3)
    assert collision(rectangle(a),rectangle(b))

def test_collision_fails_without_filtering():
    s=simulate('dense'); s['world'][50]['vehicles'][1].update(x=0,y=s['world'][50]['vehicles'][0]['y'])
    r=audit(s)
    assert r['status']=='FAIL' and r['collisions']
    assert len(s['world'][50]['vehicles'])==18

def test_identity_timestamp_teleport_and_boundary_gate():
    for mutation in ('id','timestamp','teleport','boundary'):
        s=simulate('shockwave'); f=s['world'][10]
        if mutation=='id': f['vehicles'][1]['id']='changed'
        elif mutation=='timestamp': f['timestamp_ms']=501
        elif mutation=='teleport': f['vehicles'][1]['y']+=30
        else: f['vehicles'][1]['x']=5.3
        assert audit(s)['status']=='FAIL'

def test_inertial_velocity_rotation_no_ego_subtraction():
    e=Car('ego',10,20,10,vx=10,heading_rad=math.pi/4).state()
    t=Car('t',20,30,20,vx=20,heading_rad=math.pi/4).state()
    frame=to_local({'timestamp_ms':0,'vehicles':[e,t]})
    a,b=frame['vehicles']
    assert a['vy']==pytest.approx(math.sqrt(200))
    assert b['vy']==pytest.approx(math.sqrt(800))
    assert b['x']==pytest.approx(0,abs=1e-10)
    assert b['y']==pytest.approx(math.sqrt(200))

def test_deterministic_and_observed_export_separate():
    s=simulate('yield_merge'); assert s==simulate('yield_merge')
    out=export_scene(s)
    assert len(out['timeline'])==101
    assert out['timeline'][40]['vehicle']==to_local(s['world'][80])
    assert all(tr['confidence'] is None for f in out['timeline'] for p in f['prediction']['predictions'] for tr in p['trajectories'])

def test_unsafe_request_cancelled_without_forced_motion():
    s=simulate('test',[Car('ego',0,0,20,20),Car('blocked',3.6,0,20,20,target=0,request_at=0)])
    assert s['events'][-1]['event']=='cancelled_no_safe_gap'
    assert all(f['vehicles'][1]['x']==3.6 for f in s['world'])
    assert audit(s)['status']=='PASS'

def test_near_miss_clearance_is_reported_not_filtered():
    s=simulate('test',[Car('ego',0,0,20,20),Car('near',2.5,0,20,20)])
    r=audit(s)
    assert r['min_clearance_m']==pytest.approx(.6)
    assert r['near_misses_below_1m']


def test_failed_gate_never_publishes_asset(tmp_path,monkeypatch):
    from scripts.sim_v2 import generate
    monkeypatch.setattr(generate,'ROOT',tmp_path)
    monkeypatch.setattr(generate,'audit',lambda s:{'id':s['id'],'status':'FAIL','collisions':[{'injected':True}]})
    with pytest.raises(SystemExit,match='QA FAIL'):
        generate.main()
    assert (tmp_path/'artifacts/sim_v2/QA_REPORT.json').exists()
    assert not (tmp_path/'RiskRadarPleosApp/app/src/main/assets/demo_data_v2.js').exists()

def test_uncommanded_internal_lane_crossing_fails():
    s=simulate('shockwave')
    for f in s['world']:
        f['vehicles'][1]['x']=.95
    r=audit(s)
    assert r['status']=='FAIL'
    assert r['lane_boundary_violations']
    assert not r['collisions']
