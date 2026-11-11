# SIM V2 validation ? independent PART02 recovery

Validated locally on 2026-11-11. Synthetic research only. No vehicle-control or ADAS safety capability is claimed. Work stayed in `C:\Users\Public\Documents\RiskRadarEngine02`; external executables/site-packages were used as development tools only. No commit, push, GitHub edit, PART01 source edit, PRISM team checkout edit, or RDC catalog edit was performed. Existing v1 HTML/data and the frozen PART02 RiskFrame contract are unchanged.

## Results

Physical QA: **PASS**, four deterministic 10-second worlds, 201 physical samples per scene at 50ms, 101 exported samples per scene at 100ms. All 36,783 vehicle-pair samples were checked as oriented rectangles, including ego. **0 actual body collisions; 0 near-miss samples below 1m.** Touching rectangles count as collisions. This is a discrete-time result, not a continuous collision-free proof or a claim about real driving.

| Scene | Vehicles | Pair checks | Minimum body clearance (m) | Maximum acceleration (m/s2) | Maximum jerk (m/s3) | Minimum road-edge clearance (m) |
|---|---:|---:|---:|---:|---:|---:|
| lane_change | 5 | 2,010 | 1.700000000 | 0.832147443 | 2.540629589 | 0.848970062 |
| yield_merge | 5 | 2,010 | 1.700000000 | 2.359327475 | 2.982003769 | 0.847648892 |
| shockwave | 5 | 2,010 | 1.700000000 | 4.000000000 | 2.500000000 | 0.850000000 |
| dense | 18 | 30,753 | 5.661271942 | 1.418426517 | 2.500000000 | 0.850000000 |

Maximum heading change per 50ms: 0.002298387755 rad. Maximum displacement per 50ms: 1.499947916667m. Maximum trapezoidal position/velocity residual: 0.000031354955m. No timestamp, identity, reverse-motion, road-envelope or continuity failures. Numeric gate limits: vector acceleration 4.5m/s2, vector jerk 3.5m/s3, heading step 0.04rad, step distance 2m, integration residual 0.003m. Exact unrounded values, pair/time of closest approach, failures, events and near-miss lists are in `artifacts/sim_v2/QA_REPORT.json`.

The lane changer is blocked at 1.00s by target-lane traffic, accepted at 3.60s after the fast rear vehicle passes, and finishes at 8.60s. The merger yields from 0.50s, is accepted at 1.35s, and finishes at 6.35s. The braking lead changes desired speed at 1s; follower braking propagates upstream. Dense traffic uses 18 interacting cars across three lanes.

Python: **114 passed**, including **20 new sim_v2 cases** and 94 existing PART02 cases. New regressions cover four complete demo gates, fast rear approach, slow target-lane front vehicle, delayed/completed lane change, yielding/completed merge, upstream braking response, stopped queue and cut-in, rotated bodies/clearance, injected collision rejection without filtering, changed IDs/timestamps/teleports/road departure, rotated inertial coordinates, deterministic exports/null confidence, indefinitely blocked maneuver cancellation, near-miss reporting, unauthorized internal lane crossing, and failed-QA asset publication refusal. See `artifacts/sim_v2/pytest.log`.

Node syntax checks pass for `riskradar_v2.js` and `demo_data_v2.js`. The Node DOM/canvas runtime smoke passes **1,608 sampled scene/time/viewport cases** (4 scenes �~ 201 times �~ 2 viewport stubs), playback advancement, and hypothesis/body separation. Moving every hypothesis by 1km leaves all drawn body positions unchanged. This VM check is **not browser layout or visual evidence**. See `artifacts/sim_v2/UI_RUNTIME_SMOKE.json`.

Local APK builds successfully, includes v2 HTML, JavaScript and matching data, and passes APK signature verification (v3). MainActivity loads `file:///android_asset/riskradar_v2.html`. The offline build checks QA PASS and SHA-256 matches before compilation. APK: `RiskRadarPleosApp/direct-build/RISK_RADAR_Engine02_Pleos_Debug.apk` (500,459 bytes). Build log: `artifacts/sim_v2/apk_build.log`. Existing deprecation/native-access tool warnings do not prevent the build. APK was not installed, launched on an emulator, distributed, or approved for deployment.

## Model and assumptions

Implementation: `scripts/sim_v2/model.py`, `qa.py`, `generate.py`. No randomness. Straight parallel 3.6m lanes with centers -3.6, 0, +3.6m, road envelope �}5.4m; identical 4.6 �~ 1.9m bodies. Longitudinal interaction is simplified IDM: nominal acceleration 1.5m/s2, comfortable deceleration parameter 2m/s2, desired time gap 1.35s and standstill gap 3m. Commands are limited to [-4, +1.5]m/s2 and jerk to 2.5m/s3. Low-speed braking release is bounded using remaining speed to avoid the reverse-motion defect discovered during regression development. Physical y and velocity are integrated analytically under each 50ms linear acceleration ramp. Lateral position/velocity use a five-second quintic with zero endpoint lateral velocity and acceleration. Heading follows inertial velocity; lateral and longitudinal vector bounds are independently measured by QA.

Lane changes are requested scenario intentions, not selected prediction modes. The MOBIL-like component is its safety/acceptance heuristic, not a full utility or politeness model. Before accepting, every target-lane vehicle's front/rear constant-velocity position is checked every 50ms through the full five-second maneuver. Required projected bumper gap is 8m plus 1.5 seconds of positive closing speed; estimated required rear braking must not exceed 2m/s2. Unsafe requests are delayed and retried, or cancelled at the scene end. Accepted changes reserve both source and target lanes for IDM leader response; another simultaneous request sees this reservation. An accepted maneuver finishes rather than making an abrupt mid-change abort. These CV forecasts do not bound arbitrary future acceleration or adversarial traffic. Full-world post-simulation collision QA remains mandatory and is never replaced by the lane-change heuristic.

Collision QA is independent of risk scoring: SAT over oriented body rectangles for every pair at every physical sample; exact point-to-edge Euclidean clearance for disjoint rectangles. It reports all collision samples and all clearance samples below 1m. No agent or collision is removed to pass. Full rotated body corners are checked against the outer road envelope and the current lane corridor. Only a logged, accepted five-second maneuver may reserve and cross the source/target lane corridor; otherwise the center must remain on its assigned lane center and all corners must remain inside that lane. Unauthorized internal crossings fail separately from road departures. ID order/set, sample count, timestamp sequence, reverse motion, vector acceleration/jerk, heading continuity, displacement and integration consistency are gated. Synthetic injected collisions and invalid state sequences must fail.

## Coordinates and data separation

World states are created first and saved unfiltered at 50ms in `artifacts/sim_v2/physical_world.json`. The JS asset contains 100ms `world_timeline` and a separate `timeline` of v1 `vehicle`, `prediction`, `risk` and `ego_prediction` objects. There are 404 of each frame kind. Metadata stays outside frozen frame objects.

For source ego heading ��, the world-to-local rotation is -(�� - ��/2). Positions subtract source ego world position before rotation. Velocities are **inertial velocities rotated into ego axes, never target-minus-ego relative velocities**. Ego local position is (0,0) but its velocity is nonzero. Heading is rotated by the same angle. All four demos keep ego aligned with the road; a regression also validates a rotated source ego. Prediction points remain in the fixed SOURCE ego coordinate system, not a future moving ego coordinate system.

Independent developer hypotheses use constant inertial velocity, braking, and an illustrative left-lane-change offset. They are intentionally uncalibrated alternatives and may cross road edges or one another. They do not drive any simulated body. All trajectory confidence values remain null. `prism_assess.engine.validate_input` strictly validates every exported VehicleFrame/PredictionFrame, then unchanged `assess` produces the frozen v1 RiskFrame. Ego future for risk scoring explicitly assumes five seconds of source instantaneous inertial velocity, independent of the actual future simulated ego response. PATH_OVERLAP means a candidate overlaps this assumed ego path; it is not an observed collision or collision probability.

The temporary Engine01 source is neither imported by sim_v2 nor packaged. The requested development venv is used only as a toolchain/site-packages source. No external partner PART01 payload is used, no normalization is silently applied, and compatibility with an external provider is **not asserted**. Before importing partner data, explicitly validate frozen fields, source timestamps, horizons, inertial velocity semantics and null confidence; any adapter must be separately documented and tested. Prior compatibility fixtures are not evidence for these new synthetic worlds.

## UI

Separate assets preserve v1: `demo_data_v2.js`, `riskradar_v2.html`, `riskradar_v2.js`. Bodies interpolate adjacent actual world samples at 100ms; they never interpolate a prediction candidate. Dashed translucent hypotheses for only the selected vehicle are transformed from the current source-local frame into the world camera. Ego stays on its actual sampled timeline. True body dimensions, lane widths and both axes share one meter-to-pixel scale. Playback/scrub covers 0?10s. Scenario selection, pause/reset/speed, selected-agent hypothesis toggle, risk reason, observed direction and front TTC are separate. A persistent SYNTHETIC DATA ONLY banner and research limitations remain visible. CSS targets landscape 1600�~900 and 2560�~1440; actual visual verification remains blocked below.

## Reproduction

Run in the workspace root. The requested interpreter was attempted:

```powershell
& "$env:USERPROFILE/Projects/prism-prediction-engine/.venv/Scripts/python.exe" -m scripts.sim_v2.generate
```

It fails before Python starts: `No Python at ...Python311/python.exe` (stale/malformed base-interpreter path in that external venv). Nothing in the external environment was repaired or changed. The existing documented local development fallback was used:

```powershell
$env:PYTHONPATH="$env:USERPROFILE/Projects/prism-prediction-engine/.venv/Lib/site-packages;$PWD/prism-risk-engine/src"
& 'C:/Program Files/LibreOffice/program/python.exe' -m scripts.sim_v2.generate
& 'C:/Program Files/LibreOffice/program/python.exe' -m pytest -q scripts/sim_v2 prism-risk-engine/tests --basetemp artifacts/sim_v2/test_tmp
node --check RiskRadarPleosApp/app/src/main/assets/riskradar_v2.js
node --check RiskRadarPleosApp/app/src/main/assets/demo_data_v2.js
node scripts/sim_v2/ui_runtime_smoke.cjs
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./RiskRadarPleosApp/BUILD_APK_OFFLINE.ps1
```

Generation writes the QA report and all physical states first. Any scene FAIL exits without publishing the v2 JS asset. A pre-existing asset is not overwritten on failed generation. Successful output has data/QA SHA-256 hashes in `artifacts/sim_v2/demo_manifest.json`; the offline APK build rejects changed assets/reports. `artifacts/` and `direct-build/` are existing git-ignored local outputs; no Git staging or commit was performed.

## Blockers and limits

- Exact requested Python executable is broken; 114 tests ran with the explicitly documented alternative interpreter and the requested venv's installed pytest dependencies.
- Visual browser smoke is blocked: automatic execution review rejected the direct headless Chrome launch (`blocked by policy`); the available CUA browser then returned `The browser access host is unavailable`. No security setting was changed and the rejected action was not retried through another shell. No screenshot, true browser layout, Android WebView rendering or device playback PASS is claimed. Node runtime smoke is recorded separately.
- No external PART01 provider, real dataset, sensor noise, perception uncertainty, reaction latency, road curvature, variable sizes, dynamics/tires, continuous swept-volume guarantee or safety certification is validated. Only these four finite synthetic scenes passed the 50ms physical gate.
- APK is local research output. Previous withheld user approval is not treated as deployment approval. No publication, remote change or installation occurred.
