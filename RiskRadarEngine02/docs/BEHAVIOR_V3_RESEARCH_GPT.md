# RISK RADAR ? ?? ?? ?? ????�E?? ??? ?? (ChatGPT research, 2026-11-11)

## ?? ??
?? ??? **?? ??**(?? ??, ?/? ?? ??, ?/? ??, ??, ??, ??, ??? ?? ??, ?? ?? ???)? ????, ?? ???? ???? **?? ?? ?? ??**? ????. ???? ? ?? ? ?? ?:
(1) ?? ??/??? ?????, (2) ??? ?? ?? ??, (3) ? ?? ? ??? ??.
?????? ??? ???? UNKNOWN, **OFF? ?? ???? ???**. '?? ??? ??'? '?? ??? ??' ?? ???.

## ?? ??? ??�E?? ?? ?? (2026-11-11 ??)
| ?? | ?? ?? ?? | ?? ??? ?? ?? | URL |
|---|---|---|---|
| Elios-Lab LaneChangeIntentionRecognition | ???? ?? ??/?? ??, steering/yaw/surrounding tracks+indicator | 2025 Zenodo 16686054: 50 virtual drivers, >3,400 maneuvers, CARLA, synthetic; Zenodo rights shows Copyright(c)2025 Elios Lab, **no verified broad redistribution license** | https://github.com/Elios-Lab/LaneChangeIntentionRecognition ; https://zenodo.org/records/16686054 ; https://elios-lab.github.io/LC-Intention-Framework/ |
| US DOT NGSIM | ?? ??? ???? ?? ???, 100ms tracking | 2005?06 historical data, feet->meters, FRONT-CENTER and identity time QA. Four 20s samples locally, 79,915 rows; not complete or scene-disjoint | https://data.transportation.gov/Automobiles/Next-Generation-Simulation-NGSIM-Vehicle-Trajector/8ect-6jqj |
| highD | real highways, lane change and gap selection, >110K tracked vehicles at 6 German sites | drone position records. No verified turn-signal observation; official data access/terms need review | https://www.ika.rwth-aachen.de/en/competences/projects/automated-driving/highd-dataset.html |
| INTERACTION | interactions at merges/roundabouts/intersections | source processing code BSD-3-Clause, data terms separate. Don't equate code license to trajectory rights | https://github.com/interaction-dataset/interaction-dataset ; https://interaction-dataset.com/ |
| Argoverse 2 Motion Forecasting | 250K scenarios 11s, maps and actors at 10Hz | data CC BY-NC-SA 4.0, code MIT, bulk dataset 58GB; local 26GB free => cannot fetch full. Research subsetting only | https://www.argoverse.org/av2.html |
| MTR / MTR++ | multimodal motion query, learnable intention localization and local refinement | NeurIPS 2022 paper; code Apache 2.0; training data often Waymo under separate restrictive terms; pattern study and own authorized data only | https://papers.neurips.cc/paper_files/paper/2022/hash/2ab47c960bfee4f86dfc362f26ad066a-Abstract-Conference.html ; https://github.com/sshaoshuai/MTR |
| GameFormer | multiple-agent interactive reasoning / iterative update | ICCV 2023 paper; planning/control code is OUT OF SCOPE; verify code license before copying | https://openaccess.thecvf.com/content/ICCV2023/html/Huang_GameFormer_Game-theoretic_Modeling_and_Learning_of_Transformer-based_Interactive_Prediction_and_ICCV_2023_paper.html ; https://github.com/MCZhi/GameFormer |
| nuPlan | behavior/driver baseline, reactive scenario simulation | 1200h human driving in 4 cities, scenario taxonomy. Non-commercial data restrictions; avoid production training without permission | https://www.nuplan.org/ |
| Waymo Open Motion | research paper/code architecture references only | March 2025 terms ��4 expressly prohibit data or derived model in vehicle operation/assistance or production. NO use in target car app without separate license. Code Apache does not confer data rights | https://waymo.com/open/terms/ |
| Tesla FSD fleet data | high-level comparative inspiration; not open training data | Tesla reports fleet learning from camera clips and fleet miles but no publicly licensable underlying model-training corpus was identified. Never imply Tesla FSD code/weights/data available | https://www.tesla.com/ns_videos/2024-extended-version-tesla-impact-report.pdf |

## Empirically inspected 2026-11-11
Source file `C:\Users\Public\Documents\RiskRadarOpenDataResearch\lane_change_intent_zenodo\user10LC.csv`
- Official DOI / file: https://zenodo.org/records/16686054, 3,634,189 bytes, official MD5 `b2251eca0baf5eff8ba59cd553901789` verified.
- Parsed header includes `leftDirectionIndicator,RightDirectionIndicator,steeringAngle,yawRate,vehicleSpeed,brakePedalPos,car1LatPosition,car1LongPosition,car2LatPosition,car2LongPosition,labels`.
- **Signals refer to the instrumented ego/driver vehicle, not proven for neighboring car1/car2**; there are no `car1DirectionIndicator` fields. A separate external camera/permissioned sensor is required to observe another car's indicator.
- Raw `labels` values and units must be interpreted against documentation; no assumption that numeric values are calibrated probabilities.
- Archive lists copyright notice. Store raw locally, never commit or deploy trained model without license review.
- The NGSIM dataset has no verified vehicle blinker channel in the previously examined public columns: `indicator_state=UNKNOWN` for real neighboring traffic.

## Required new sidecar interface (proposed only)
`BehaviorObservations v0` every 100ms:
`{schema_version:'0.1-research', source_timestamp_ms, coordinate_system:'ego_local_m', tracks:[{vehicle_id, observation_timestamp_ms, indicator_state:'LEFT|RIGHT|OFF|UNKNOWN', indicator_source:'EXPLICIT_SENSOR|CAMERA_CLASSIFIER|SYNTHETIC|UNAVAILABLE', indicator_quality:null|0..1, lateral_offset_m, lateral_v_mps, lateral_a_mps2, yaw_rate_radps, nearest_lane_boundary_m, track_age_s, perception_stale_ms, ...}]}`
- Preserve all pre-existing frozen PART01/02 schemas. This sidecar never invents an ADAS observation.
- Unobserved indicator UNKNOWN; observed OFF only if actual sensor detects OFF. Synthetic labels must retain explicit SYNTHETIC provenance. No signal alone triggers red warning.
- `BehaviorIntentFrame v0`: expected set KEEP/PREPARE_LEFT/PREPARE_RIGHT/CHANGE_LEFT/CHANGE_RIGHT/ABORT_LEFT/ABORT_RIGHT/BRAKE/YIELD/UNKNOWN; time-to-lane-boundary estimate/interval, observation quality and reasons; `score` not a calibrated probability without held-out calibration.
- `RiskFrame v1` remains separate and unchanged, with future overlap candidate and TTC geometry. Predicting an unsafe lane entry is not the same as planning/braking.

## First-stage model stack
A. Interpretable causal, past-only baseline: lateral displacement/velocity/acceleration and yaw trend, track history 2?5s, indicator state/missingness, relative front/rear gaps and closing speed, lane topology; median smoothing and track expiry. Treat repeated on/off as undecided; detect interruption/reversal.
B. Optional state model (HMM/finite state), with explicit entry/exit hysteresis and calibrated probabilities only after proper training data. Compare against CV/CA and team PART01 hypotheses.
C. More complex MTR/GameFormer-inspired multi-agent context after (A/B) measured validity; do not use restricted WOD derivatives in vehicle.
D. Output early, non-intrusive WATCH when position+closing context support it; WARNING only if objective overlap/time-to-conflict conditions plus quality; UNKNOWN on sensor limitations. All thresholds config/experimental, no real safety claim.

## Coverage cases that must be individually tested
(1) blinker on no lane change, (2) on and cancel, (3) on then delayed, (4) on + correct turn, (5) on wrong side, (6) no signal gentle entry, (7) no signal sudden cut-in, (8) repeated indecision, (9) aborted mid-change, (10) false camera-indicator detection,
(11) no indicator accessible, (12) missing/stale observations, (13) ID switch/occlusion, (14) road curvature, (15) stopped traffic, (16) rear fast closure, (17) target-lane slow front, (18) two cars simultaneously cross lane, (19) truck/bus different body sizes, (20) merging lane end, (21) multiple-agent ripple braking, (22) lane departure then recovery, (23) heavy traffic, (24) sudden gap opening, (25) parallel non-threat, (26) negative yaw noise, (27) varied road widths, (28) non-synchronized timestamp, (29) missing lane map, (30) scene shift and changed geography.

## Evaluation standards
- Source-scene/session/site-disjoint splits to prevent leakage; keep driver IDs separate for CARLA.
- Report intent precision/recall/AUPRC, per-class confusion, early lead time at fixed false-alert/hour, missed dangerous cut-ins, crossing-time error, observed/synthetic status and total events. Separate retrospective hindsight metrics from deployable past-only metrics.
- Risk assess compare TTC-only vs interaction+trajectory and error/missing-data abstention. Do not turn heuristic scores into 'collision probability' without calibration.
- Evaluate feature availability: signal-observed subset and signal-unavailable subset. Native Pleos app cannot infer other road users in real time without actual authorized object tracking, so research and offline demonstration remain distinct.

**Git push blocked pending user approval; no current or future work in this doc authorizes deployment.**
