# Behavior V3 isolated implementation ? 2026-11-11

Research baseline delivered before the 09:30 Asia/Seoul deadline. No network,
Git commit/push, APK publication or vehicle integration. Existing Engine02,
VehicleFrame/PredictionFrame/RiskFrame v1, sim_v2, data_quality and V2 assets were
not edited by this work. The checkout already contained partner changes; these
were left in place. Optional Android HTML was omitted, so production MainActivity
has no new dependency or asset reference.

## Deliverables and status

| Deliverable | Status | Exact location |
|---|---|---|
| Stdlib causal inference, independent BehaviorIntentFrame v0 | PASS (research contract) | `scripts/behavior_v3/intent.py` |
| Data adapter/replacement contract, no PART01 imports/API | PASS | `scripts/behavior_v3/README.md` |
| Offline metrics and strict temporal/group holdout checks | PASS (synthetic tests) | `scripts/behavior_v3/evaluation.py` |
| Counterexample and sequence tests | PASS, 72 test cases | `prism-risk-engine/tests/test_behavior_v3.py` |
| Existing tests plus V3 plus unmodified sim_v2 regression | PASS, 204 tests total | `scripts/behavior_v3/results/pytest.log`, `pytest.xml` |
| Physical gate, replay and metrics | PASS (bounded synthetic smoke) | `scripts/behavior_v3/results/smoke.json` |
| SHA256 input/output and local NGSIM row inventory | Recorded | `scripts/behavior_v3/results/manifest.json` |
| Real-data held-out accuracy/calibration and upgrade comparison | BLOCKED | See limitations below |
| Optional UI / HMM / trained model | Not implemented | Optional work deliberately omitted |

Files written are restricted to `scripts/behavior_v3/**`, the single new V3 test
file, and this document. Test temporary directories stay under
`scripts/behavior_v3/test_tmp` and `runtime_tmp`; bytecode and pytest cache writes are disabled by
the commands below. `inventory.py` reads existing local CSV files only to record
headers/counts/hashes; they are not used as fitted data or accuracy evidence.

## Behavior and uncertainty

The input sidecar has measured road-relative kinematics, fixed initial lane
reference, identity epoch, optional contemporaneous front event, same-timestamp
neighbors, and explicit indicator/provenance. Indicator UNKNOWN is not OFF.
SYNTHETIC remains labeled. Ambiguous BOTH/hazards are UNKNOWN. No likelihood or
confidence is calibrated; bounded left/right support explicitly says
**heuristic score not calibrated**. Every parameter is **EXPERIMENTAL**.

Lateral velocity, leading body-edge proximity and road-relative yaw feed smooth
support scores. Discrete rules produce KEEP, PREPARE_LEFT/RIGHT,
CHANGE_LEFT/RIGHT, ABORT_LEFT/RIGHT, BRAKE, YIELD and UNKNOWN. Indicator alone
can produce PREPARE but cannot produce CHANGE or physical danger geometry.
BRAKE comes from past speed differences; YIELD additionally requires preparation
and a measured adjacent closing interaction. Front-event labels alone cannot
fabricate braking. A frame's features never use subsequent samples or event labels.
There is no HMM or Bayesian transition layer.

State is keyed by track ID with explicit identity epochs, a monotonic reception
clock, track expiry, stale-frame rejection, warmup, finite/dimension/velocity
checks, backward acceleration checks and position/velocity residual checks.
Unreliable lane geometry, teleportation and reassociation yield UNKNOWN. No
missing samples are interpolated. Duplicate/out-of-order frames cannot overwrite
trusted state. Small smooth ID swaps remain an upstream tracker limitation.

The risk geometry output separately contains measured current OBB overlaps,
sampled constant-velocity hypothetical overlaps, and front/rear/adjacent bumper
gaps with closing speed and longitudinal TTC. A CV candidate never becomes an
actual collision flag or collision probability. Empty neighbor coverage carries
uncertainty, not a safe-road claim. Local tangent OBB projection is approximate
on curved roads; the adapter must supply road-relative motion and mark unreliable
geometry UNKNOWN. See README for signs, origins, units and all field semantics.

## Measured smoke results

Reused unmodified `scripts/sim_v2/model.py` and `qa.py`. Four scenes, 804 physical
50ms samples, **36,783 unordered physical pair checks**, **zero sampled physical
collisions**, 6,633 track-frame inferences. Every discovered physical collision
or other existing V2 physical-QA failure raises an error before a smoke success
report can be written. Four injected collision timestamps (including endpoints)
are tested. Prediction-overlap metadata cannot change the physical gate.

Events are observed leading-body-edge crossings of each track's fixed initial
lane line, derived offline from physical trajectories; simulator request/accepted
events are not truth labels for intention and never enter inference. Candidate
episode onsets are PREPARE/CHANGE starts, matched by track/direction, earliest
onset within 3s before crossing, once per event. The 100..7000ms cohort excludes
warmup and permits complete trailing horizons through 10000ms. The smoke fails
if a crossing falls outside the scored interval rather than silently counting a
censored event as a false alert. Exposure counts the actual 50ms scored samples
per observed track, including ego (0.0637083333 track-hours).

| Synthetic smoke metric | Measured value |
|---|---:|
| True observed crossing events / matched events | 2 / 2 |
| Precision / recall / miss rate | 1.0 / 1.0 / 0.0 |
| False candidate episodes / track-hour | 0 / 0.0637083333 = 0.0 |
| Early warning lead times | 0.90s, 0.95s |
| Mean early warning lead time | 0.925s |
| CV time-to-line estimates at candidate onset | 2.014945s, 2.047819s |
| CV time-to-line overestimation | 1.114945s, 1.097819s |
| Current geometry vs independent observed physical OBBs | TP=0, FP=0, FN=0, TN=73,566 directed pairs |
| CV risk zones vs future observed physical OBB overlap | TP=0, FP=0, FN=0, TN=50,874 directed pair-horizons |

CV risk-zone evaluation compares any overlap at 0.25..2.0s samples with independent
future physical OBBs at those same sample times, only in offline evaluation.
These collision-free scenes contain **no positive overlap examples**; zero FP/FN
does not validate collision prediction, sensitivity or safety. Two scripted lane
crossings do not establish real-data accuracy or statistical calibration. The
CV time-to-line error demonstrates the effect of accelerating lateral motion.
Signal-only preparation may create false candidate episodes on other data;
counterexample tests enforce its separation from geometry and CHANGE.

## Test coverage and reproducibility

The 72 V3 cases include constant lane, no-signal rapid cut-in in both directions,
observed signal with no change, tentative reversal/abort, both blinkers,
unavailable/inferred/synthetic signals, observed OFF, missing observation, latency,
future/duplicate/delayed frames, expiry, clock rollback, track age, ID churn,
teleport and identity epochs, lane-reference changes, road-relative curvature,
rear approach, adjacent slow front, simultaneous merge, measured overlap,
projected-only overlap, asynchronous/duplicate neighbors, braking, front-event
counterexample, yielding, body-edge time-to-line, yaw extent, backward acceleration,
invalid dimensions/nonfinite data, smooth score continuity, prefix invariance,
JSON contract, no runtime PART01 imports, one-to-one event metrics, empty labels,
temporal/site/recording/driver leakage, split boundaries/overlapping windows,
all four V2 scene physical gates and injected collisions at four timestamps.

Run these exact PowerShell commands from
`C:\Users\Public\Documents\RiskRadarEngine02` (no install/network required):

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH="$env:USERPROFILE/Projects/prism-prediction-engine/.venv/Lib/site-packages;$PWD/prism-risk-engine/src"
New-Item -ItemType Directory -Force scripts/behavior_v3/runtime_tmp | Out-Null
$env:TMPDIR=(Resolve-Path scripts/behavior_v3/runtime_tmp).Path
$env:TEMP=$env:TMPDIR
$env:TMP=$env:TMPDIR
& 'C:/Program Files/LibreOffice/program/python.exe' -m pytest -q prism-risk-engine/tests scripts/sim_v2/test_sim_v2.py -p no:cacheprovider --basetemp=scripts/behavior_v3/test_tmp --junitxml=scripts/behavior_v3/results/pytest.xml 2>&1 | Tee-Object -FilePath scripts/behavior_v3/results/pytest.log
& 'C:/Program Files/LibreOffice/program/python.exe' -m scripts.behavior_v3.smoke
& 'C:/Program Files/LibreOffice/program/python.exe' -m scripts.behavior_v3.inventory
```

Focused tests: replace the two pytest collection paths above with
`prism-risk-engine/tests/test_behavior_v3.py`. Actual full regression: **204 passed**
(72 new V3 + 132 preexisting test cases). The plain `python` executable is not on
PATH; the existing documented LibreOffice interpreter plus existing pytest
site-packages was used. No Python environment was repaired or installed.

Manifest hashes identify exact sources, test logs, smoke results, read-only V2
inputs and four local NGSIM 20s CSV windows with counts/headers. The manifest
does not hash itself and does not imply raw-data publication or legal approval.
Re-running tests changes timing-bearing XML/log hashes; regenerate the manifest
after the smoke and tests. Runtime contains no PART01 or engine import; offline
QA imports sim_v2 only when invoked.

## Blockers and next acceptance gate

No verified real intention labels, stable real lane-relative geometry, known
driver identities or legally cleared train/validation/test groups were supplied
for this implementation. Four local 20s NGSIM windows are inventory-only; no
real held-out accuracy, ADE/FDE, calibration or driver-disjoint claim is made.
Data rights/indicator verification and raw trajectory QA remain the other task
owners' work. Unknown indicator channels remain UNKNOWN.

`temporal_holdout` assigns by absolute time before fitting, then rejects any
site/recording/driver reused across splits and any overlapping same-recording
windows. Embargo is configurable. Unknown driver identity blocks a claimed
driver-disjoint result. There is no fitted normalization in this baseline.
Consumers must split raw groups before deriving windows or fitting any future
normalizer. Independent scene/driver labels and permitted real test data are
required before comparing upgrades; synthetic smoke cannot select a model for
vehicle deployment. No AV2/Waymo training download, Tesla weights or desktop
multi-GPU training was attempted.
