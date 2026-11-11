# Behavior V3 observation contract (research only)

This isolated Python baseline exports **BehaviorIntentFrame v0**. It does not
import PART01, register a vehicle API, change RiskFrame v1, or integrate with
MainActivity. Consumers can replace temporary PART01 later by implementing the
observation adapter described here. There is no steering/braking/HUD interface.
Python inference uses only the standard library. pytest is a development tool.

## Input: one Observation sidecar per track timestamp

All distances are meters, times integer milliseconds in one monotonic acquisition
domain, velocities m/s, angles radians. Positions are **body centers**, not front
bumpers. `d` is rightward and `s` forward in road coordinates; `yaw_rad` is
clockwise from the road tangent. `vd_mps` and `vs_mps` are road-relative inertial
velocities, not ego-relative closing velocities. Upstream adapters must transform
positions, yaw and velocities consistently and remove road curvature from lateral
motion. A raw world x velocity is not a lane-change feature on a curved road.

Required: `track_id`, `timestamp_ms`, `d_m`, `s_m`, `vd_mps`, `vs_mps`.
Defaults for other fields are visible in `intent.py`; they are assumptions for
synthetic smoke, not verified dimensions or geometry for an arbitrary dataset.
Real adapters must explicitly supply observed dimensions, yaw and lane geometry.
Use `reliable=False` or `lane_geometry_reliable=False` when unavailable.
`observe(None, now_ms=..., missing_track_id=...)` represents a missing observation.

- `lane_center_d_m`, `lane_width_m`, `lane_reference`: **fixed initial lane**
  reference throughout a maneuver. Do not recenter on the nearest lane every
  frame. A reference change resets history and returns UNKNOWN for that sample.
- `identity_epoch`: change when a tracker reassociates an ID. Namespace IDs by
  site/recording/session. A teleport or implausible acceleration resets history;
  an unflagged physically plausible ID swap cannot be detected reliably here.
- `indicator`: LEFT / RIGHT / OFF / UNKNOWN. `indicator_provenance`: OBSERVED /
  SYNTHETIC / UNKNOWN. Missing, BOTH/hazard lights, ambiguous or unrecognized values
  become UNKNOWN, never OFF. Only a measured OFF may carry OBSERVED. A synthetic
  signal remains explicitly flagged and cannot become ground truth or confidence.
- `front_event`: contemporaneous BRAKING / NONE / UNKNOWN observation, never a
  future simulator command or label. It is exposed as context; it does not invent
  braking without measured deceleration.
- `neighbors`: tuple of Neighbor sidecars in the same coordinates and **exact same
  acquisition timestamp**. Duplicate IDs, self, invalid or asynchronous neighbors
  are omitted with uncertainty. No neighbors means unknown coverage, not a safe
  empty road. Neighbors are provided as a snapshot, independent of processing order.
- `now_ms`: nondecreasing reception clock in the acquisition time domain. Future,
  stale, duplicate, out-of-order and excessively frequent frames return UNKNOWN;
  rejected frames never overwrite trusted history. Missing data is not interpolated.

```python
from scripts.behavior_v3 import IntentEngine, Observation

engine = IntentEngine()
for t, d in [(0, 0.0), (100, -0.08)]:
    observation = Observation('replay/car7', t, d, t*.02, -.8, 20.,
                              indicator='UNKNOWN', indicator_provenance='UNKNOWN')
    frame = engine.observe(observation, now_ms=t)
    print(frame.to_dict())
```

## Output and interpretation

`motion_intention` is KEEP, PREPARE_LEFT/RIGHT, CHANGE_LEFT/RIGHT,
ABORT_LEFT/RIGHT, BRAKE, YIELD or UNKNOWN. This is current motion evidence and
optional preparation context, not a calibrated future event likelihood.
`scores.LEFT/RIGHT` are bounded **heuristic score not calibrated**; no confidence
or collision probability is emitted. All parameters are **EXPERIMENTAL**.
There is no HMM/Bayesian smoothing or trained model.

Features use the current measured snapshot and previous accepted observation only:
fixed-lane lateral offset/velocity, backward acceleration differences,
road-relative yaw, leading oriented-body-edge distance and CV time-to-line,
track age, front event and indicator availability/provenance. Neighbor bumper gaps,
closing speeds, side/front/rear classification and longitudinal TTC are in
`risk_geometry.neighbor_gaps`. Longitudinal TTC is not a collision TTC when lanes
are separated. No derivative or normalization uses future frames.

The smoothstep motion support spans 0.08..0.65m/s; signal support is 0.34. Preparation
and change cutoffs are 0.32 and 0.60. Thus signal alone permits preparation but
never CHANGE. Deceleration <= -1.5m/s2 permits BRAKE; YIELD additionally requires
preparation evidence and a measured closing adjacent interaction (longitudinal
TTC <4s). Reversal following preparation while displaced permits ABORT. These
names describe deterministic rules, not verified mental intent. An indicator
without motion is not an actionable warning. Class cutoffs are discrete even
though support scores are smooth.

`risk_geometry` is independent of the intention class:

- `observed_body_overlap_ids`: current oriented rectangle overlap from observations.
  This is a geometry flag, not proof of contact in noisy real sensing. UNKNOWN
  from invalid/missing track data has status UNAVAILABLE and null overlaps.
- `cv_projected_overlap`: constant-velocity hypothetical body intersections sampled
  every 0.25s over 2s. This never marks a current/actual collision. It has no
  uncertainty envelope or probability. Sampling can miss between-sample contacts.
- Available geometry during a valid track's warmup remains a snapshot; intention
  stays UNKNOWN until 100ms. Staleness >250ms and track expiry >1000ms are explicit.

OBBs use a local road-tangent plane, not a curved-road swept volume. Unknown lane
geometry must suppress inference. The caller owns map alignment, sensor coverage,
timestamps, ID integrity and units. No output should control a vehicle.

## Offline evaluation boundary

`evaluation.py` alone accepts observed labels. Inference never imports it.
`Event` labels represent observed leading-body-edge crossing of an initial lane
line, not simulator requested/accepted maneuvers. Alert episode onsets match by
track AND direction within 0..3s before the event, one to one. Unmatched alert
episodes are false alerts; unmatched events are misses. Lead time and CV time-to-line
are different quantities. Exposure is valid observed **track-hours**, not scene
wall-clock hours. Exclude warmup, missing coverage and boundary-censored horizons;
never compare these rates directly with a wall-clock fleet alert rate.

`temporal_holdout` assigns whole windows by absolute temporal boundaries before
any feature fitting; `validate_holdout` rejects overlapping recording windows,
embargo violations, shared site/recording/known driver across partitions, unknown
drivers and non-temporal partitions. Supply true driver identity: a local track ID
is not a driver identity. Split raw groups before creating windows or fitting
normalization. Baseline has no fitted normalization. No legal-data eligibility is
inferred from a filesystem path. Real upgrade comparisons require verified rights,
group-disjoint labels, sufficient events and untouched real test partitions.

`require_physical_pass` reuses unmodified sim_v2 QA; every discovered physical body
collision is fatal, as are other physical QA failures. Prediction overlap does
not enter this gate. The smoke evaluates current OBB overlap against independent
sim_v2 rectangles and CV candidates against future observed OBB overlap as
**offline labels only**. Collision-free smoke has no positive collision examples.

See `docs/BEHAVIOR_V3_IMPLEMENTATION.md` for actual measurements, exact commands,
ownership, limitations and artifacts. No large dataset downloads or GPU work.
