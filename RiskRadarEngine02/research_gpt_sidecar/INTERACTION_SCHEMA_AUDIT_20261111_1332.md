# INTERACTION official schema and signal provenance audit — 2026-11-11 13:32 KST

## Scope and verification level

Independent ChatGPT **public-source, read-only** verification. Desktop `DO` was reported **offline** by the Remote Desktop Commander device listing (last seen 18 minutes before check); **no Windows files, CLI sessions, RAM/CPU/disk values, scheduled-task logs, or new datasets were observed**. No CARLA/NGSIM/INTERACTION dataset was downloaded. This is a research plan, not a code/test execution result.

## New actionable finding: turn-indicator supervision is unavailable in the documented INTERACTION recorded vehicle-track schema

The dataset maintainers' Hugging Face page describes recorded per-vehicle CSV columns:

`track_id, frame_id, timestamp_ms, agent_type, x, y, vx, vy, psi_rad, length, width`.

Units documented there: timestamp in **milliseconds**, coordinates `x,y` in **metres**, velocity `vx,vy` in **metres/second**, yaw in **radians**, vehicle length/width in **metres**. Track IDs restart for each recorded vehicle CSV file. Only trajectories/maps are provided in that release description; **no recorded turn-indicator/neighbor signal column is specified**.

**Consequence for Engine02:** when adapting an INTERACTION neighbor track to `Observation`, set `indicator=UNKNOWN`, `indicator_provenance=UNKNOWN` unless a separately authorized and directly observed signal source exists. Never invent `OFF` from the absence of a field; do not infer a true 'no-signal cut-in' label from a lateral trajectory. Observed lateral motion may allow an operational `CHANGE_LEFT/RIGHT` heuristic hypothesis, but not ground-truth indicator-based intent or collision probability.

Position/velocity are in the dataset's local XY coordinates, **not automatically road-relative Frenet `s,d`**. Geometry adaptation must use verified lane geometry/HD maps (Lanelet2) to derive road-relative features and attach `lane_reference`; absent trustworthy mapping, set `lane_geometry_reliable=False` and return UNKNOWN. Composite track identity must include source/scenario, recording CSV, track_id and a recording time window; `track_id` alone is not globally unique. Avoid overlapping windows across held-out splits.

Candidate protocol for event-level validation: independently identify roadway geometry and lane-boundary crossings; require observed past prefix only; separate event labels from source-frame rows; annotate maneuver completion and abort explicitly with clear labeling rules; use scenario/recording/agent-disjoint groups and embargo. Do not report event precision/recall, ADE/FDE or false alarms/hour from this study without valid labeled exposure.

## Rights and provenance

**CODE LICENSE:** Maintainer GitHub repository `interaction-dataset/interaction-dataset` README explicitly says its Python script **package** is BSD 3-Clause (separate `LICENSE` file). This statement does **not** grant blanket rights to redistribute the recorded trajectory dataset.

**DATA LICENSE:** The dataset distribution/usage terms for the recorded tracks were **not verified as an unconditional permissive data license** in this check. The older `interaction-dataset.com` access page mentions a manually reviewed request; maintainers' official Hugging Face page now states it is the primary host and the old site is being sunset. Because those access methods differ, **do not assume approval or commercial/redistribution rights**. No dataset download, Git mirroring or training until version-specific terms are independently confirmed. Store source and license state per file in provenance manifest when authorized.

## Grounded sources (accessed 2026-11-11)

1. Dataset-maintainer distribution and recorded CSV schema: https://huggingface.co/datasets/INTERACTION-dataset/INTERACTION-dataset
2. Maintainer code package and BSD-3-Clause statement: https://github.com/interaction-dataset/interaction-dataset
3. Historic access form, **not authoritative for a new HF-hosted release**: https://interaction-dataset.com/about/
4. Challenge task settings (one second past/three seconds future, **separate task context**, not a rule for arbitrary train/test splits): https://challenge.interaction-dataset.com/

## Status

- Public dataset schema and code-license distinction: VERIFIED from public source descriptions.
- Per-vehicle signal visibility: **NOT PROVIDED IN DOCUMENTED SCHEMA**; adjacent signals UNKNOWN.
- Full dataset redistribution / ML usage terms: **PENDING**.
- Local DO resource state, Codex/Hermes execution, new physical regression or real-data benchmark: **BLOCKED/NOT MEASURED** due to device offline.
- No real-world ADAS safety claim; no team PRISM or frozen RiskFrame changes.
