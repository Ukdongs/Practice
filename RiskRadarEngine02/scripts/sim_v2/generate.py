"""Run QA before publishing separate assets. No PART01 imports or normalization."""
import json
import hashlib
import math
from pathlib import Path
import sys
from .model import SCENES, simulate, to_local, smooth
from .qa import audit
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'prism-risk-engine'/'src'))
from prism_assess.engine import assess, validate_input

TITLES={'lane_change':('Wait for the rear gap','A fast rear vehicle passes before a lane change is accepted.'),
    'yield_merge':('Yield, then merge','The merging vehicle slows while priority traffic clears.'),
    'shockwave':('Braking travels upstream','A lead vehicle slows; followers respond through car following.'),
    'dense':('Traffic in balance','18 vehicles interact across three lanes with bounded controls.')}

def hypotheses(frame):
    """Independent kinematic hypotheses in SOURCE ego axes, never actual motion."""
    predictions=[]
    for v in frame['vehicles']:
        if v['id']==frame['ego_id']: continue
        trajectories=[]
        for mode in ('lane_keep','braking','lane_change_left'):
            points=[]
            for h in range(1,6):
                forward=v['vy']*h
                if mode=='braking':
                    stop=min(h,max(0,v['vy'])/2.)
                    forward=v['vy']*stop-stop*stop
                lateral=-3.6*smooth(h/5) if mode=='lane_change_left' else 0.
                points.append({'dt_ms':h*1000,'x':v['x']+v['vx']*h+lateral,
                               'y':v['y']+forward,'heading_rad':v['heading_rad']})
            trajectories.append({'mode':mode,'confidence':None,'points':points})
        predictions.append({'vehicle_id':v['id'],'trajectories':trajectories})
    result={'schema_version':'1.0','timestamp_ms':frame['timestamp_ms'],'predictions':predictions}
    validate_input(frame,result)
    return result

def export_scene(scene):
    timeline=[]
    for physical in scene['world'][::2]:
        vehicle=to_local(physical); prediction=hypotheses(vehicle)
        ego=next(v for v in vehicle['vehicles'] if v['id']=='ego')
        path={'source_timestamp_ms':vehicle['timestamp_ms'],'coordinate_system':'ego_local_m',
              'points':[{'dt_ms':h*1000,'x':ego['vx']*h,'y':ego['vy']*h,'heading_rad':ego['heading_rad']} for h in range(1,6)]}
        risk,_=assess(vehicle,prediction,path)
        timeline.append({'vehicle':vehicle,'prediction':prediction,'risk':risk,'ego_prediction':path})
    title,description=TITLES[scene['id']]
    return {'id':scene['id'],'title':title,'description':description,'duration_ms':10000,'step_ms':100,
        'provenance':'SYNTHETIC DATA ONLY; local sim_v2 IDM-like world; no PART01 runtime or data import',
        'ego_future_assumption':'Source instantaneous inertial velocity held constant for 5s; NOT actual future ego motion',
        'timeline':timeline,'world_timeline':scene['world'][::2],'events':scene['events']}

def main():
    out=ROOT/'artifacts'/'sim_v2'; out.mkdir(parents=True,exist_ok=True)
    scenes=[simulate(s) for s in SCENES]
    reports=[audit(s) for s in scenes]
    report={'status':'PASS' if all(r['status']=='PASS' for r in reports) else 'FAIL',
        'physical_step_ms':50,'export_step_ms':100,'duration_ms':10000,'seed':0,
        'scope':'All physical sample pairs, oriented rectangles; discrete 50ms gate, not continuous proof',
        'scenes':reports}
    (out/'QA_REPORT.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    # Preserve every physical state even on failure; never filter overlaps.
    (out/'physical_world.json').write_text(json.dumps(scenes,separators=(',',':'),allow_nan=False),encoding='utf-8')
    print(json.dumps(report,indent=2))
    if report['status']!='PASS': raise SystemExit('QA FAIL: assets not published')
    data=[export_scene(s) for s in scenes]
    (ROOT/'RiskRadarPleosApp/app/src/main/assets/demo_data_v2.js').write_text(
        'window.RISK_RADAR_V2 = '+json.dumps(data,separators=(',',':'),allow_nan=False)+';\n',encoding='utf-8')
    (out/'demo_manifest.json').write_text(json.dumps({'qa_status':'PASS','scenes':list(SCENES),
        'asset_sha256':hashlib.sha256((ROOT/'RiskRadarPleosApp/app/src/main/assets/demo_data_v2.js').read_bytes()).hexdigest(),
        'qa_sha256':hashlib.sha256((out/'QA_REPORT.json').read_bytes()).hexdigest(),
        'vehicle_frames':404,'prediction_frames':404,'risk_frames':404,'confidence':None,
        'prediction_provider':'sim_v2 independent DEV kinematic hypotheses; strict PART02 v1 validator',
        'normalization':'No external PART01 input; no adapter applied. External provider compatibility NOT asserted.'},indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()
