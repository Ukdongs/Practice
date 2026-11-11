"""Independent all-pairs oriented body gate on 50ms physical samples."""
import math
from itertools import combinations
from .model import DT, LANES

def rectangle(v):
    co,si=math.cos(v['heading_rad']),math.sin(v['heading_rad'])
    return [(v['x']+u*co-w*si,v['y']+u*si+w*co) for u,w in
        [(-v['length_m']/2,-v['width_m']/2),(v['length_m']/2,-v['width_m']/2),
         (v['length_m']/2,v['width_m']/2),(-v['length_m']/2,v['width_m']/2)]]

def collision(a,b):
    for p in (a,b):
        for q,r in zip(p,p[1:]+p[:1]):
            axis=(-(r[1]-q[1]),r[0]-q[0])
            pa=[x*axis[0]+y*axis[1] for x,y in a]; pb=[x*axis[0]+y*axis[1] for x,y in b]
            if max(pa)<min(pb) or max(pb)<min(pa): return False
    return True

def point_segment(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    u=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-u*dx,p[1]-a[1]-u*dy)

def clearance(a,b):
    if collision(a,b): return 0.
    return min(point_segment(p,q,r) for src,dst in ((a,b),(b,a)) for p in src for q,r in zip(dst,dst[1:]+dst[:1]))

def audit(scene):
    failures=[]; collisions=[]; near=[]; minimum=1e9; closest=None; boundary=1e9
    maxa=maxj=maxh=maxstep=maxres=0.; pairs=0; previous=None; prev_acc={}
    lane_violations=[]
    initial_lanes={v['id']:min(LANES,key=lambda x:abs(x-v['x'])) for v in scene['world'][0]['vehicles']}
    expected=tuple(v['id'] for v in scene['world'][0]['vehicles'])
    if len(set(expected))!=len(expected) or 'ego' not in expected: failures.append('invalid initial IDs')
    if len(scene['world'])!=201: failures.append('expected 201 physical samples')
    for i,frame in enumerate(scene['world']):
        t=frame['timestamp_ms']; vs=frame['vehicles']
        if t!=i*50: failures.append(f'timestamp:{t}')
        if tuple(v['id'] for v in vs)!=expected: failures.append(f'IDs:{t}')
        polys={v['id']:rectangle(v) for v in vs}
        for v in vs:
            if not all(math.isfinite(v[k]) for k in ('x','y','vx','vy','heading_rad','length_m','width_m')): failures.append(f'nonfinite:{t}')
            margin=min(5.4-abs(x) for x,y in polys[v['id']]); boundary=min(boundary,margin)
            # Check lane discipline separately from the outer road boundary.
            # Only accepted physical maneuvers may cross an internal lane boundary.
            lane=initial_lanes.get(v['id'],min(LANES,key=lambda x:abs(x-v['x'])))
            corridor=(lane-1.8,lane+1.8); changing=False
            for event in scene['events']:
                if event['id']!=v['id'] or event['event']!='accepted' or event['time_ms']>t: continue
                target=event['target_x']
                if t < event['time_ms']+5000:
                    corridor=(min(lane,target)-1.8,max(lane,target)+1.8); changing=True
                else:
                    lane=target; corridor=(lane-1.8,lane+1.8)
            invalid=(not changing and abs(v['x']-lane)>1e-6) or any(x<corridor[0]-1e-6 or x>corridor[1]+1e-6 for x,y in polys[v['id']])
            if invalid:
                lane_violations.append({'time_ms':t,'id':v['id'],'corridor_x':corridor})
                failures.append(f'lane_boundary:{t}:{v["id"]}')
            if margin<0: failures.append(f'road_boundary:{t}:{v["id"]}')
            if v['vy']<-.001: failures.append(f'reverse:{t}:{v["id"]}')
            if previous and v['id'] in previous:
                p=previous[v['id']]; acc=((v['vx']-p['vx'])/DT,(v['vy']-p['vy'])/DT)
                maxa=max(maxa,math.hypot(*acc))
                if v['id'] in prev_acc:
                    old=prev_acc[v['id']]; maxj=max(maxj,math.hypot(acc[0]-old[0],acc[1]-old[1])/DT)
                prev_acc[v['id']]=acc
                maxh=max(maxh,abs(math.remainder(v['heading_rad']-p['heading_rad'],2*math.pi)))
                maxstep=max(maxstep,math.hypot(v['x']-p['x'],v['y']-p['y']))
                residual=math.hypot(v['x']-p['x']-.5*(v['vx']+p['vx'])*DT,v['y']-p['y']-.5*(v['vy']+p['vy'])*DT)
                maxres=max(maxres,residual)
        for a,b in combinations(vs,2):
            pairs+=1; pa,pb=polys[a['id']],polys[b['id']]
            hit=collision(pa,pb); d=clearance(pa,pb)
            if d<minimum: minimum=d; closest={'time_ms':t,'ids':[a['id'],b['id']]}
            if hit: collisions.append({'time_ms':t,'ids':[a['id'],b['id']]})
            elif d<1.: near.append({'time_ms':t,'ids':[a['id'],b['id']],'clearance_m':d})
        previous={v['id']:v for v in vs}
    limits={'acceleration_mps2':4.5,'jerk_mps3':3.5,'heading_step_rad':.04,'position_residual_m':.003,'step_m':2.}
    for key,value in [('acceleration_mps2',maxa),('jerk_mps3',maxj),('heading_step_rad',maxh),('position_residual_m',maxres),('step_m',maxstep)]:
        if value>limits[key]: failures.append(f'{key}:{value}')
    if collisions: failures.append('ACTUAL_BODY_COLLISION')
    return {'id':scene['id'],'status':'FAIL' if failures else 'PASS','samples':len(scene['world']),
        'pair_checks':pairs,'collisions':collisions,'near_misses_below_1m':near,'min_clearance_m':minimum,
        'closest_pair':closest,'min_road_boundary_clearance_m':boundary,'max_acceleration_mps2':maxa,
        'max_jerk_mps3':maxj,'max_heading_step_rad':maxh,'max_step_m':maxstep,'max_position_residual_m':maxres,
        'lane_boundary_violations':lane_violations,'limits':limits,'failures':failures,'events':scene['events']}
