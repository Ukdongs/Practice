"""Causal interpretable baseline. All thresholds are EXPERIMENTAL, not calibrated.

Road coordinates: d right, s forward, yaw clockwise from road tangent. A fixed
lane reference must remain attached to a track throughout a maneuver. No labels,
future trajectories, PART01 modules, or vehicle control interfaces are imported.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class Parameters:
    """EXPERIMENTAL SI thresholds; fixed a priori, no fitting/normalization."""
    expiry_ms: int = 1000
    max_latency_ms: int = 250
    warmup_ms: int = 100
    min_dt_ms: int = 20
    max_speed_mps: float = 80.
    max_lateral_mps: float = 8.
    max_acceleration_mps2: float = 15.
    max_residual_m: float = 1.5
    horizon_s: float = 2.
    projection_step_s: float = .25
    prepare_score: float = .32
    change_score: float = .60
    brake_mps2: float = -1.5


@dataclass(frozen=True)
class Neighbor:
    track_id: str
    timestamp_ms: int
    d_m: float
    s_m: float
    vd_mps: float
    vs_mps: float
    length_m: float = 4.6
    width_m: float = 1.9
    yaw_rad: float = 0.


@dataclass(frozen=True)
class Observation:
    track_id: str
    timestamp_ms: int
    d_m: float
    s_m: float
    vd_mps: float
    vs_mps: float
    yaw_rad: float = 0.
    lane_center_d_m: float = 0.
    lane_width_m: float = 3.6
    length_m: float = 4.6
    width_m: float = 1.9
    indicator: str = 'UNKNOWN'
    indicator_provenance: str = 'UNKNOWN'
    front_event: str = 'UNKNOWN'  # BRAKING / NONE / UNKNOWN, contemporaneous
    reliable: bool = True
    lane_geometry_reliable: bool = True
    identity_epoch: str = '0'  # change on tracker reassociation
    lane_reference: str = 'fixed-road-lane'
    neighbors: tuple[Neighbor, ...] = ()  # measured at exactly this timestamp


@dataclass(frozen=True)
class BehaviorIntentFrame:
    track_id: str
    timestamp_ms: int
    motion_intention: str
    scores: dict
    features: dict
    risk_geometry: dict
    uncertainty: tuple[str, ...]
    reasons: tuple[str, ...]
    schema_version: str = 'BehaviorIntentFrame v0'
    research_only: bool = True
    score_semantics: str = 'heuristic score not calibrated'
    parameter_status: str = 'EXPERIMENTAL'

    def to_dict(self):
        return asdict(self)


@dataclass
class _State:
    observation: Observation
    first_ms: int
    previous_direction: str | None = None
    previous_accel: float | None = None


def ramp(value, low, high):
    """C1 smoothstep, bounded heuristic support, NOT probability."""
    u = max(0., min(1., (value - low) / (high - low)))
    return u * u * (3 - 2 * u)


def _finite(*values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) for v in values)


def _body(d, s, length, width, yaw):
    co, si = math.cos(yaw), math.sin(yaw)
    return [(d + x*co + y*si, s - x*si + y*co)
            for x, y in ((-width/2, -length/2), (width/2, -length/2),
                         (width/2, length/2), (-width/2, length/2))]


def _overlap(a, b):
    for poly in (a, b):
        for p, q in zip(poly, poly[1:] + poly[:1]):
            ax, ay = q[1]-p[1], p[0]-q[0]
            aa = [x*ax+y*ay for x, y in a]
            bb = [x*ax+y*ay for x, y in b]
            if max(aa) < min(bb) or max(bb) < min(aa):
                return False
    return True


def _valid_neighbor(n, o, p):
    return (n.track_id != o.track_id and bool(n.track_id)
            and n.timestamp_ms == o.timestamp_ms
            and _finite(n.d_m, n.s_m, n.vd_mps, n.vs_mps,
                        n.length_m, n.width_m, n.yaw_rad)
            and 0.5 <= n.length_m <= 30 and .3 <= n.width_m <= 5
            and abs(n.vs_mps) <= p.max_speed_mps
            and abs(n.vd_mps) <= p.max_lateral_mps)


def geometry(o, neighbors, p):
    """Tangent-plane OBBs; CV projection is a hypothesis, never observed truth.

    Curved-road long-horizon geometry must be transformed by an upstream map
    adapter; this local approximation makes no collision-probability claim.
    """
    observed, projected, gaps = [], [], []
    body = _body(o.d_m, o.s_m, o.length_m, o.width_m, o.yaw_rad)
    steps = max(1, math.ceil(p.horizon_s / p.projection_step_s))
    for n in neighbors:
        if _overlap(body, _body(n.d_m, n.s_m, n.length_m, n.width_m, n.yaw_rad)):
            observed.append(n.track_id)
        first = None
        for k in range(1, steps + 1):
            t = min(p.horizon_s, k*p.projection_step_s)
            if _overlap(_body(o.d_m+o.vd_mps*t, o.s_m+o.vs_mps*t,
                              o.length_m, o.width_m, o.yaw_rad),
                        _body(n.d_m+n.vd_mps*t, n.s_m+n.vs_mps*t,
                              n.length_m, n.width_m, n.yaw_rad)):
                first = t
                break
        if first is not None:
            projected.append({'track_id': n.track_id, 'first_sample_s': first})
        delta = n.s_m-o.s_m
        gap = abs(delta)-(o.length_m+n.length_m)/2
        closing = o.vs_mps-n.vs_mps if delta >= 0 else n.vs_mps-o.vs_mps
        gaps.append({'track_id': n.track_id,
                     'side': 'LEFT' if n.d_m < o.d_m-1. else
                             'RIGHT' if n.d_m > o.d_m+1. else 'SAME',
                     'position': 'FRONT' if delta >= 0 else 'REAR',
                     'bumper_gap_m': gap, 'closing_mps': closing,
                     'longitudinal_ttc_s': max(0., gap)/closing if closing > .01 else None})
    return {'status': 'AVAILABLE', 'observed_body_overlap_ids': observed,
            'cv_projected_overlap': projected, 'neighbor_gaps': gaps,
            'horizon_s': p.horizon_s, 'step_s': p.projection_step_s,
            'semantics': 'local tangent OBB geometry; CV hypothesis, no collision probability'}


class IntentEngine:
    def __init__(self, parameters=None):
        self.parameters = parameters or Parameters()
        p = self.parameters
        if not (_finite(*asdict(p).values())
                and 0 < p.min_dt_ms <= p.warmup_ms < p.expiry_ms
                and p.max_latency_ms >= 0 and 0 < p.projection_step_s <= p.horizon_s
                and 0 <= p.prepare_score < p.change_score <= 1
                and p.max_speed_mps > 0 and p.max_lateral_mps > 0
                and p.max_acceleration_mps2 > 0
                and p.max_residual_m > 0):
            raise ValueError('Invalid EXPERIMENTAL parameters')
        self._states: dict[str, _State] = {}
        self._watermark = -1

    def _unknown(self, ident, timestamp, reason):
        return BehaviorIntentFrame(ident, timestamp, 'UNKNOWN', {}, {},
                                   {'status': 'UNAVAILABLE', 'observed_body_overlap_ids': None,
                                    'cv_projected_overlap': None}, (reason,), (reason,))

    def observe(self, observation: Observation | None, *, now_ms: int,
                missing_track_id: str = '') -> BehaviorIntentFrame:
        """One track timestamp at a time, monotonic reception clock required.

        Same-timestamp neighbors may be supplied in any track processing order.
        Rejected frames never overwrite trusted history. Explicit identity changes
        reset history; an undetectable smooth ID swap remains a tracker limitation.
        """
        if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0 or now_ms < self._watermark:
            return self._unknown(missing_track_id if observation is None else observation.track_id,
                                 now_ms, 'nonmonotonic_clock')
        self._watermark = now_ms
        p = self.parameters
        for ident in list(self._states):
            if now_ms-self._states[ident].observation.timestamp_ms > p.expiry_ms:
                del self._states[ident]
        if observation is None:
            return self._unknown(missing_track_id, now_ms, 'missing_observation')
        o = observation
        unknown = lambda reason: self._unknown(o.track_id, o.timestamp_ms, reason)
        if (not isinstance(o.timestamp_ms, int) or isinstance(o.timestamp_ms, bool)
                or o.timestamp_ms < 0 or not isinstance(o.track_id, str) or not o.track_id
                or not o.identity_epoch or not o.lane_reference):
            return unknown('invalid_identity_or_timestamp')
        if o.timestamp_ms > now_ms or now_ms-o.timestamp_ms > p.max_latency_ms:
            return unknown('future_or_stale_frame')
        if not o.reliable or not o.lane_geometry_reliable:
            self._states.pop(o.track_id, None)
            return unknown('unreliable_observation_or_lane')
        if (not _finite(o.d_m, o.s_m, o.vd_mps, o.vs_mps, o.yaw_rad,
                        o.lane_center_d_m, o.lane_width_m, o.length_m, o.width_m)
                or not .5 <= o.length_m <= 30 or not .3 <= o.width_m <= 5
                or not 2. <= o.lane_width_m <= 6.
                or abs(o.vs_mps) > p.max_speed_mps or abs(o.vd_mps) > p.max_lateral_mps):
            self._states.pop(o.track_id, None)
            return unknown('invalid_kinematics_or_dimensions')
        state = self._states.get(o.track_id)
        if state and o.timestamp_ms <= state.observation.timestamp_ms:
            return unknown('duplicate_or_out_of_order')
        if state and (o.identity_epoch != state.observation.identity_epoch
                      or o.lane_reference != state.observation.lane_reference
                      or o.lane_center_d_m != state.observation.lane_center_d_m
                      or o.lane_width_m != state.observation.lane_width_m):
            self._states[o.track_id] = _State(o, o.timestamp_ms)
            return unknown('identity_or_lane_reference_reset')
        ad = along = None
        if state:
            prev = state.observation
            dt = (o.timestamp_ms-prev.timestamp_ms)/1000
            if dt*1000 < p.min_dt_ms:
                return unknown('sampling_interval_too_short')
            residual = math.hypot(o.d_m-prev.d_m-(prev.vd_mps+o.vd_mps)*dt/2,
                                  o.s_m-prev.s_m-(prev.vs_mps+o.vs_mps)*dt/2)
            if residual > p.max_residual_m:
                self._states[o.track_id] = _State(o, o.timestamp_ms)
                return unknown('track_discontinuity')
            ad = (o.vd_mps-prev.vd_mps)/dt
            along = (o.vs_mps-prev.vs_mps)/dt
            if math.hypot(ad, along) > p.max_acceleration_mps2:
                self._states.pop(o.track_id, None)
                return unknown('implausible_acceleration')
        else:
            state = _State(o, o.timestamp_ms)
        age = (o.timestamp_ms-state.first_ms)/1000
        uncertainty = []
        provenance = o.indicator_provenance
        indicator = o.indicator
        if provenance not in ('OBSERVED', 'SYNTHETIC') or indicator not in ('LEFT', 'RIGHT', 'OFF'):
            indicator, provenance = 'UNKNOWN', 'UNKNOWN'
            uncertainty.append('indicator_unobserved')
        if provenance == 'SYNTHETIC':
            uncertainty.append('synthetic_indicator_research_only')
        ids = [n.track_id for n in o.neighbors]
        valid = tuple(n for n in o.neighbors if _valid_neighbor(n, o, p) and ids.count(n.track_id) == 1)
        if len(valid) != len(o.neighbors):
            uncertainty.append('invalid_or_unsynchronized_neighbors_omitted')
        if not valid:
            uncertainty.append('neighbor_coverage_unknown')
        offset = o.d_m-o.lane_center_d_m
        # Oriented lateral half extent; distance to line is leading body edge.
        extent = abs(math.cos(o.yaw_rad))*o.width_m/2 + abs(math.sin(o.yaw_rad))*o.length_m/2
        distances = {'LEFT': o.lane_width_m/2+offset-extent,
                     'RIGHT': o.lane_width_m/2-offset-extent}
        ttl, scores = {}, {}
        for direction, sign in (('LEFT', -1), ('RIGHT', 1)):
            speed = sign*o.vd_mps
            ttl[direction] = max(0., distances[direction])/speed if speed > .05 else None
            # Signal alone can support preparation but never CHANGE or geometry.
            motion = ramp(speed, .08, .65)
            near = 1-ramp(max(0., distances[direction]), .1, 1.5)
            yaw = ramp(sign*o.yaw_rad, .015, .12)
            scores[direction] = min(1., .72*motion + .16*near*motion + .12*yaw*motion
                                    + (.34 if indicator == direction else 0.))
        direction = max(scores, key=scores.get)
        score = scores[direction]
        reasons = []
        label = 'KEEP'
        prior = state.previous_direction
        returning = prior and ((prior == 'LEFT' and o.vd_mps > .08)
                               or (prior == 'RIGHT' and o.vd_mps < -.08))
        if age*1000 < p.warmup_ms:
            label = 'UNKNOWN'
            uncertainty.append('track_warmup')
        elif returning and abs(offset) > .12:
            label = 'ABORT_'+prior
            reasons.append('motion_reversed_after_preparation')
        elif score >= p.change_score and abs(o.vd_mps) > .08:
            label = 'CHANGE_'+direction
            reasons.append('lateral_motion_toward_boundary')
        elif along is not None and along <= p.brake_mps2:
            # YIELD requires braking AND a measured closing adjacent interaction.
            interacting = any(g['side'] != 'SAME' and g['longitudinal_ttc_s'] is not None
                              and g['longitudinal_ttc_s'] < 4
                              for g in geometry(o, valid, p)['neighbor_gaps'])
            label = 'YIELD' if interacting and (prior or score >= p.prepare_score) else 'BRAKE'
            reasons.append('observed_deceleration_with_interaction' if label == 'YIELD'
                           else 'observed_deceleration')
        elif score >= p.prepare_score:
            label = 'PREPARE_'+direction
            reasons.append('weak_motion_or_optional_indicator')
        if label.startswith(('PREPARE_', 'CHANGE_')):
            prior = direction
        elif label.startswith('ABORT_') or (abs(offset) < .12 and abs(o.vd_mps) < .08):
            prior = None
        self._states[o.track_id] = _State(o, state.first_ms, prior, along)
        features = {'lateral_offset_m': offset, 'lateral_velocity_mps': o.vd_mps,
                    'lateral_acceleration_mps2': ad, 'longitudinal_acceleration_mps2': along,
                    'yaw_relative_road_rad': o.yaw_rad, 'time_to_line_s': ttl,
                    'body_distance_to_line_m': distances, 'track_age_s': age,
                    'indicator': indicator, 'indicator_provenance': provenance,
                    'indicator_observed': provenance == 'OBSERVED',
                    'front_event': o.front_event if o.front_event in ('BRAKING', 'NONE') else 'UNKNOWN'}
        return BehaviorIntentFrame(o.track_id, o.timestamp_ms, label, scores, features,
                                   geometry(o, valid, p), tuple(uncertainty), tuple(reasons))
