"""Deterministic physical world. +x right, +y forward, headings from +x."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math

DT = .05
LANES = (-3.6, 0., 3.6)
DURATION = 10.

def clamp(x, lo, hi): return max(lo, min(hi, x))
def smooth(u):
    u = clamp(u, 0., 1.)
    return u**3 * (10 - 15*u + 6*u*u)
def dsmooth(u):
    return 30*u*u*(1-u)**2 if 0 < u < 1 else 0.

@dataclass
class Car:
    id: str
    x: float
    y: float
    vy: float
    desired: float = 23.
    ay: float = 0.
    vx: float = 0.
    heading_rad: float = math.pi/2
    length_m: float = 4.6
    width_m: float = 1.9
    target: float | None = None
    request_at: float = 1.
    change_start: float | None = None
    origin: float | None = None
    duration: float = 5.

    def state(self):
        return {k: getattr(self, k) for k in ('id','x','y','vx','vy','heading_rad','length_m','width_m','ay')}

def occupants(c):
    return (c.origin, c.target) if c.change_start is not None else (min(LANES, key=lambda x: abs(x-c.x)),)

def acceleration(c, cars, desired=None):
    """IDM with conservative dual-lane occupancy during an accepted change."""
    v0 = max(.1, c.desired if desired is None else desired)
    a = min(1.5*(1-(c.vy/v0)**4), .8*(v0-c.vy))
    for other in cars:
        if other.id == c.id or other.y <= c.y: continue
        if not set(occupants(c)).intersection(occupants(other)): continue
        gap = max(.2, other.y-c.y-(other.length_m+c.length_m)/2)
        wanted = 3. + max(0., c.vy*1.35+c.vy*(c.vy-other.vy)/(2*math.sqrt(1.5*2.)))
        a = min(a, 1.5*(1-(c.vy/v0)**4-(wanted/gap)**2))
    return max(clamp(a, -4., 1.5), -math.sqrt(3.*max(0.,c.vy)))

def safe_change(c, cars, target):
    """Front AND rear CV trajectories every 50ms across the full maneuver.

    Gap > 8m plus closing-speed margin; rear braking demand <= 2m/s2.
    This is a deterministic acceptance heuristic, not a safety proof.
    """
    for o in cars:
        if o.id == c.id or target not in occupants(o): continue
        for k in range(int(c.duration/DT)+1):
            t = k*DT
            d = o.y + o.vy*t - c.y - c.vy*t
            gap = abs(d)-(o.length_m+c.length_m)/2
            closing = max(0., c.vy-o.vy if d >= 0 else o.vy-c.vy)
            if gap < 8.+closing*1.5: return False
        if o.y < c.y:
            gap = c.y-o.y-(o.length_m+c.length_m)/2
            if max(0., o.vy-c.vy)**2/(2*max(.1,gap-3.)) > 2.: return False
    return True

def scene_cars(name):
    if name == 'lane_change':
        return [Car('ego',0,0,22),Car('changer',0,55,23,target=-3.6),
                Car('fast_rear',-3.6,45,30,30),Car('target_front',-3.6,145,28,28),Car('right',3.6,35,22)]
    if name == 'yield_merge':
        return [Car('ego',0,0,21,22),Car('merger',3.6,55,19,22,target=0,request_at=.5),
                Car('priority',0,60,24,24),Car('rear',0,-45,21,22),Car('left',-3.6,25,22)]
    if name == 'shockwave':
        return [Car('ego',0,0,22,24),Car('response',0,55,22,24),Car('brake_lead',0,110,22,24),
                Car('left',-3.6,15,23),Car('right',3.6,55,22)]
    if name == 'dense':
        return [Car('ego',0,0,19,21)]+[Car(f'dense_{lane}_{i}',x,i*36+(lane-1)*10,19+(i%2),21)
            for lane,x in enumerate(LANES) for i in range(-2,4) if not (lane==1 and i==0)]
    raise ValueError(name)

SCENES = ('lane_change','yield_merge','shockwave','dense')

def simulate(name, cars=None):
    cars = scene_cars(name) if cars is None else cars
    frames, events = [], []
    delayed = set()
    for tick in range(201):
        t = tick*DT
        for c in cars:
            if c.target is not None and c.change_start is None and t >= c.request_at:
                if safe_change(c,cars,c.target):
                    c.change_start=t; c.origin=c.x
                    events.append({'time_ms':round(t*1000),'id':c.id,'event':'accepted','target_x':c.target})
                elif c.id not in delayed:
                    delayed.add(c.id)
                    events.append({'time_ms':round(t*1000),'id':c.id,'event':'delayed_unsafe_front_or_rear'})
        frames.append({'timestamp_ms':round(t*1000),'vehicles':[c.state() for c in cars]})
        if tick == 200: break
        wanted = []
        for c in cars:
            desired = c.desired
            if name == 'shockwave' and c.id == 'brake_lead' and t >= 1.: desired = 5.
            # Yield by seeking a lower speed until the priority vehicle opens a gap.
            if name == 'yield_merge' and c.id == 'merger' and c.change_start is None: desired = 16.
            wanted.append(acceleration(c,cars,desired))
        for c, a in zip(cars,wanted):
            new_a = c.ay + clamp(a-c.ay,-2.5*DT,2.5*DT)
            j = (new_a-c.ay)/DT
            c.y += c.vy*DT + .5*c.ay*DT**2+j*DT**3/6
            c.vy += c.ay*DT+.5*j*DT**2
            c.ay = new_a
            if c.change_start is not None:
                u = (t+DT-c.change_start)/c.duration
                c.x = c.origin+(c.target-c.origin)*smooth(u)
                c.vx = (c.target-c.origin)*dsmooth(u)/c.duration
                if u >= 1.:
                    c.x=c.target; c.vx=0.; c.target=None; c.change_start=None; c.origin=None
            if math.hypot(c.vy,c.vx)>1e-6: c.heading_rad = math.atan2(c.vy,c.vx)
    for c in cars:
        if c.target is not None and c.change_start is None:
            events.append({'time_ms':10000,'id':c.id,'event':'cancelled_no_safe_gap'})
    return {'id':name,'world':frames,'events':events}

def to_local(frame):
    """Translate positions; rotate inertial velocity WITHOUT subtracting ego velocity."""
    ego = next(v for v in frame['vehicles'] if v['id']=='ego')
    angle = ego['heading_rad']-math.pi/2
    co, si = math.cos(angle), math.sin(angle)
    vehicles=[]
    for v in frame['vehicles']:
        dx,dy=v['x']-ego['x'],v['y']-ego['y']
        vehicles.append({'id':v['id'],'x':co*dx+si*dy,'y':-si*dx+co*dy,
            'vx':co*v['vx']+si*v['vy'],'vy':-si*v['vx']+co*v['vy'],
            'heading_rad':v['heading_rad']-angle,'length_m':v['length_m'],'width_m':v['width_m'],
            'lane_id':'L'+str(1+min(range(3),key=lambda i:abs(LANES[i]-v['x'])))})
    return {'schema_version':'1.0','timestamp_ms':frame['timestamp_ms'],
            'coordinate_system':'ego_local_m','ego_id':'ego','vehicles':vehicles}
