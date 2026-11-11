# RISK RADAR Engine02 — Waymo official license and deployment gate

**Audit date:** 2026-11-11 13:48 KST. Independent public official-source check; no dataset, model, or source code downloaded. DO Remote Desktop Commander was **offline** at this check (device last seen ~33 minutes before), so **local RAM, CPU, disk, running agent/process state and scheduler logs were NOT VERIFIED**. No Codex or Hermes local work can be claimed as completed in this run.

## New finding: research-only dataset and derived model restriction

Waymo's current official **Waymo Dataset License Agreement for Non-Commercial Use (March 2025)** at https://waymo.com/open/terms/ restricts use of the dataset, any model refined/trained on it, and its model weights in (i) the operation or assistance of operation of a vehicle, (ii) Production Systems, or (iii) primarily commercial purposes. Production Systems in the agreement include systems meant to provide products or services to others **even without monetary compensation**. The page also describes conditions on dataset redistribution and derivatives. This is a **dataset/model usage restriction**, not identical to the software code license.

Waymo's official dataset about page https://www.waymo.com/open/about/ says the data are mixed manual/autonomous operations and should only be used for research, **not evaluation of real-life performance of any specific vehicle**.

The official `waymo-research/waymo-open-dataset` project repository README at https://github.com/waymo-research/waymo-open-dataset states that most code is **Apache-2.0**, but `src/waymo_open_dataset/wdl_limited` subfolders have additional limited terms. The **dataset itself is separately licensed** and cannot be presumed Apache-2.0 merely because the repo is.

## Concrete Engine02 gate

- `WOD_DATA_ACCESS=HOLD`, `WOD_DERIVED_MODEL_TO_REAL_VEHICLE=PROHIBITED_UNDER_REVIEWED_LICENSE`, `WOD_MODEL_OR_DATA_TO_PRODUCTION=PROHIBITED_UNDER_REVIEWED_LICENSE`.
- Do not download or train on Waymo data for Engine02 real vehicle alert/control, even if experiments or a demo are unpaid; do not distribute raw Waymo files/models on team or personal Git.
- Pure academic, offline, authorized noncommercial research may be separately assessed after the intended usage and full dataset/version-specific conditions are verified; not authorized automatically by this document.
- Use only independently developed source code with its own license reviewed; if reusing any limited-license `wdl_limited` component, perform an additional code license check.
- No real held-out ADE/FDE, intent precision/recall, lead-time or false-alerts/hour measured. No actual road-safety conclusion.

## Sources checked

1. **Official license**: https://waymo.com/open/terms/
2. **Official research-only / real vehicle performance disclaimer**: https://www.waymo.com/open/about/
3. **Official code-license distinction**: https://github.com/waymo-research/waymo-open-dataset and https://github.com/waymo-research/waymo-open-dataset/blob/master/LICENSE

## Outcome

- Official public data-license and code-license split: **PASS — evidence reviewed**.
- Waymo data for vehicle-operation assistance/production systems: **HOLD / NOT PERMITTED under reviewed terms**.
- DO local execution, Codex CLI and Hermes: **BLOCKED — offline**.
- No new input files or binary assets, no modifications to PRISM, frozen RiskFrame v1, or notebook/FORM NEXT. This note is research-only in `research_gpt_sidecar`.
