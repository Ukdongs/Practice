# RISK RADAR Engine02 — Argoverse 2 license and motion forecasting schema gate

Audit time: 2026-11-11 14:04 KST (Asia/Seoul). One independent official-public-source research task only. **DO Desktop Commander offline** in the first device check, last seen 49 minutes earlier. Local RAM/CPU/disk, scheduled task, Codex/Hermes activity and prior test reruns **NOT VERIFIED**. No download or execution on DO, no raw data uploaded, no edits to the team PRISM repo or frozen RiskFrame v1.

## Confirmed license split

- Argoverse 2 trajectory DATA and associated documentation: **CC BY-NC-SA 4.0**, noncommercial scope with attribution/share-alike requirements. The official Terms and Conditions specifically describe noncommercial use; access without paying for data is not a grant for commercial model training or vehicle-product development.
- Argoverse code/API: **MIT**. That license is not automatically inherited by the recorded trajectories or by trained models built using restricted inputs.
- For Engine02, keep `AV2_DATA_TRAINING=HOLD_PENDING_PURPOSE_REVIEW` and `AV2_PRODUCT_OR_VEHICLE_USE=HOLD_NONCOMMERCIAL_TERMS`. Do not fold noncommercial-data-trained weights or derivatives into a deployable commercial/vehicle feature without independent legal clearance. Noncommercial academic research may be considered separately according to the complete terms.
- Do not upload data, derived samples, frames, maps, pretrained weights or restricted assets to personal/team Git. Official source: https://argoverse.github.io/user-guide/terms_and_conditions.html ; https://www.argoverse.org/av2.html .

## Confirmed official AV2 motion forecasting schema

- 250,000 scenario descriptions from six cities. Each described scenario is 11 seconds. Scenario metadata: `scenario_id`, `timestamps_ns`, `tracks`, `focal_track_id`, `city_name`. Official code schema also exposes `map_id`, `slice_id`.
- Track fields: `track_id`, `object_states`, `object_type`, `category`. Per-object-state fields: `observed`, `timestep`, `position` (XY **center of bounding box**), `heading` (map-frame radians), `velocity` (XY m/s). `timestamps_ns` are nanoseconds, while `timestep` is an index. Do not treat `timestep` as milliseconds or directly use it to calculate speed.
- The categories `TRACK_FRAGMENT`, `UNSCORED_TRACK`, `SCORED_TRACK`, `FOCAL_TRACK` denote challenge scoring / track quality, NOT behavioral maneuver ground truth (ABORT, SIGNAL_ONLY, etc.). `observed` distinguishes observed segment in benchmark data; evaluation must enforce past-only inference, even when future states exist in the file.
- No turn-indicator field exists in the documented `ObjectState` schema. For an engine adapter, set `indicator=UNKNOWN`, `indicator_provenance=UNKNOWN` for each track, absent an independently authorized observed source. Cannot infer unobserved turn-signal OFF, SIGNAL_ONLY, or NO_SIGNAL_CUTIN ground-truth labels.
- Map-frame XY center cannot be mapped directly to road-frame (`s,d`) or to NGSIM front-center coordinates. A tested map/lane transformer and an explicit center-origin contract are prerequisites; without reliable lanes set `lane_geometry_reliable=False` and fail conservatively to UNKNOWN.

## Adversarial contract test suggestions (specifications, NOT executed)

1. `scenario_id=A, track_id=7` and `scenario_id=B, track_id=7` must remain distinct actors; split by scenario and provenance, not track_id alone.
2. `timestep=10` with `timestamps_ns` spacing of 100,000,000 must imply 0.1 s, not 10 ms or 10 s.
3. A `FOCAL_TRACK` category is not a maneuver-intention label, and `SCORED_TRACK` is not a positive risky-driving event.
4. A position at the bounding-box **center** must not be passed as **front center**; vehicle length affects front-center offset (and yaw/heading orientation).
5. An unobserved future track state (`observed=False`) must not enter causal features available at the current prediction time.
6. A track's absent turn-signal field yields `UNKNOWN`, never `OFF`; avoid claiming signal-only or no-signal cut-ins as fully supervised outcomes.
7. A failed HD map/lane conversion sets `lane_geometry_reliable=False`; the inference frame should return UNKNOWN rather than counterfeit road-relative positions.

## Sources (official, accessed 2026-11-11)

- Official Terms and Conditions: https://argoverse.github.io/user-guide/terms_and_conditions.html
- Official Motion Forecasting guide: https://argoverse.github.io/user-guide/tasks/motion_forecasting.html
- Maintainer's formal data schema, MIT-licensed source: https://github.com/argoverse/av2-api/blob/main/src/av2/datasets/motion_forecasting/data_schema.py
- Official download / data license overview: https://www.argoverse.org/av2.html

## Status

- Official license/schema review: **PASS (documentary evidence)**.
- Dataset acquisition / code adapter / new regression test: **NOT RUN** (DO offline; no raw data requested).
- Independent real trajectory ADE/FDE, event precision-recall, lead time, false alerts per track-hour: **NOT MEASURED**.
- Git upload of this text-only sidecar document: subject to separate remote verification.
