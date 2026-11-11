# RISK RADAR ? dataset acquisition & risk safety quality plan (2026-11-11)

Source provenance: official US DOT NGSIM / official INTERACTION code & dataset pages / Argoverse 2 and Waymo official terms. This is a RESEARCH PLAN, not proof of on-road safety, regulatory compliance, or model accuracy.

## Fundamental limitation
No finite dataset can enumerate "all possible road situations" or guarantee collision prevention. This prototype has NO sensor fusion, braking control, authority to influence actual vehicle behavior, or validated ADAS. It must never use measured trajectory replay as a live warning system.

## Already secured on desktop DO (do NOT copy bulk CSV into public Git)
Directory: `C:\Users\Public\Documents\RiskRadarOpenDataResearch`
- Official US DOT NGSIM Source: https://data.transportation.gov/Automobiles/Next-Generation-Simulation-NGSIM-Vehicle-Trajector/8ect-6jqj/data
- 4 �~ contiguous 20-second windows at i-80, us-101, lankershim, peachtree; CSV and SHA256 manifest.
- ~79,915 rows total; deliberately small research excerpts, not complete dataset.
- Approx 2,329 forecast cases from two highway windows; these are not scene-disjoint train/test splits.
- Temporary / team PART01 *CV* mean ADE@1..5s 2.478m; FDE@5s 4.973m. *CA* mean ADE 6.908~6.909m; FDE 15.402~15.404m. Numbers essentially identical between engines for these bare baselines; full multi-candidate engine/model superiority NOT established. CA performs worse in this sample, do not automatically prioritize it.
- NGSIM raw source observations may be noisy/inconsistent and are not authoritative ground-truth collision labels. Critical feet��meters, reference-point, sign, temporal ordering and ID-convention QA precede use.
- Research directory raw data is excluded from repository.

## Dataset catalog & rights
1. US DOT NGSIM: synchronized cameras, 100ms original tracks, public catalog, metadata. Research/developer baseline; legal metadata lists CC BY-SA 3.0 for catalog's dataset distribution. Source: https://catalog.data.gov/dataset/next-generation-simulation-ngsim-vehicle-trajectories-and-supporting-data ; validate specific export, attribution and derivative requirements before distribution. This is historical 2005?2006 traffic and has known measurement limitations.
2. INTERACTION: actual vehicle tracks at 11 locations, multilane merge/lane-change and roundabouts/intersections; Python tools BSD-3-Clause are distinct from *underlying data* rights. Download small approved tracks only after reading dataset terms. Sources https://interaction-dataset.com and https://github.com/interaction-dataset/interaction-dataset ; https://huggingface.co/datasets/INTERACTION-dataset/INTERACTION-dataset.
3. Argoverse 2 Motion Forecasting: 250,000 11-second scenarios (10Hz), six US cities, HD maps. Official archive ~58 GB: larger than desktop's currently available 26GB, so no whole-dataset download. CC BY-NC-SA 4.0 for data, MIT code. Use only permitted scene subsets after reviewing competition/company use implications. Source https://www.argoverse.org/av2.html .
4. Waymo Motion: 103,354 motion scenarios, multiple actors/city road geometry; **DO NOT download/retrain/deploy for in-vehicle use** unless special permissions/terms expressly allow it. Waymo dataset license forbids using data and derivatives to operate/assist a vehicle and production systems; code Apache-2.0 is not a grant to redistribute data. Sources https://waymo.com/open/about/ https://waymo.com/open/terms/ .
5. highD, inD, rounD: additional highway/intersection/roundabout candidates. Access and redistribution terms must be checked on official provider sites before download. Not imported. Do not infer that their code license covers motion recordings.

## Parallel ownership (avoids simultaneous file writes)
- GPT Chat / research: source URL, official license, scenario coverage matrix, measurement conventions, sample and split guidance. May edit ONLY `docs/DATASET_RESEARCH_AND_SAFETY_PLAN.md`.
- RDC / data execution: bounded official NGSIM downloads in `RiskRadarOpenDataResearch`, SHA256 and scientific audit logs under local `artifacts`; no uploads of raw data and no data deletions.
- Codex CLI / isolated implementation: only `scripts/data_quality/*`, `prism-risk-engine/tests/test_data_quality.py`, `docs/DATA_QUALITY_GATE.md`; offline data quality CLI and 15+ regression tests.
- Hermes / read-only independent safety audit: challenge 50ms discrete collision checks, target-lane rear gap, candidate-vs-observed separation, uncertainty, false-alarm cases, dataset leakage and unsafe UI claims. No file writes.

## Required independent safety gates
Gate A �E Data consent/license and provenance per dataset version: source, DOI, download URL, checksum, transformations, allowed use, redistribution. Unclear rights => research hold; never commit raw frames.
Gate B �E Unit conversion and geometry: feet vs meters; NGSIM front-center vs body-center; orientation; map/road provenance; split track IDs by site/recording.
Gate C �E Real observations quality: 100ms continuity, no duplicate time/id, physical dimensions, yaw/heading, velocity vs coordinate delta, unknown lane mapping, noise/dropout; quarantine failing tracks. Recorded collisions require independent annotation, never assume zero.
Gate D �E Simulation physical world: no sampled oriented-body overlap at 50ms; bounded acceleration, jerk and road departure; continuous swept volumes or high-rate substep QA for crossing events; regressions for fast rear, aggressive cut-in, stalled vehicle, merges and emergency braking.
Gate E �E Predictive forecast evaluation: disjoint by scene/site/date/source; report per-class ADE/FDE@1/3/5s, missed interaction, distribution shifts and source confounding. Never select best hypothesis with future truth as if deployable. Keep calibration separate.
Gate F �E Risk decision validation: compare TTC-only, TTC+occupied area, multiagent; train and evaluate on different events. Report false alerts/hr, missed imminent encounters, time-to-warning, stale track and UNKNOWN coverage; confidence calibration and appropriate abstention.
Gate G �E Android: offline scenario replay distinct from real-time input; dataset label visible; no unjustified collision probability or red safety-critical instruction. On-target performance and driver distraction before release.
Gate H �E Go/no-go: no real vehicle alerts without legal sensor access, independently verified ground-truth labels, proven fail-safe behavior, security/privacy review and target hardware evaluation.

## Coverage matrix for expansion
Road type: straight/curved, freeway/city, 2~5 lanes, merging/ramp/split, intersection/crosswalk, roundabout, roadwork.
Actor type: sedan/SUV/truck/bus/motorbike/cyclist/pedestrian/unknown, dimensions & classes.
Interactions: tailgating, lead sudden braking, rear approach, cut-in/cut-out, blind-spot, multi-lane cascade, lateral crossing, yield, blocked merge, stop-and-go, queue, zipper merge, simultaneous lane changes, U-turn.
Observability: missing / stale/noisy ID, partial occlusion, changed track id, inconsistent velocity, uncertain lanes, unobserved ego future, time clock offset.
Environment: rain/snow/fog, night, curves, road gradient, lighting, sensors degraded. **These dimensions require genuinely representative instrumented data, not mere 2D synthetic positions.**
Traffic regime: rare events, high occupancy, severe congestion, unusual speeds, stopped vehicle, other road users.
Physical violations: body overlap, road departure, unrealistic acceleration/jerk, teleport. Tests should fail closed and never clip away colliding agents.

## Critical distinction
Data volume improves statistical coverage but does not, by itself, establish vehicle crash prevention or calibrated risk. Safety requires representative and clean data, strong held-out evaluation, sensor authority, uncertainty-aware abstention, hardware performance, and safety engineering.

## Immediate next experiment
- Keep older v1 screen unchanged; run V2 `riskradar_v2.html` with PHYSICAL QA certificate alongside 11 synthetic scenarios (4 physical-world + 7 team HighwayEnv scenes).
- Demonstrate selected candidate hypothesis in dashed lines without moving actual simulated body.
- Run isolated CLI QA on four 20s NGSIM windows (existing data) and quarantine bad track IDs before any replay import.
- Compare both PART01 engines using the exact same legally usable held-out scenes, not test counts.
- Generate a user-reviewed demo, then ask for approval BEFORE any Git push/merge.
