# RISK RADAR Engine02 — 2026-11-11 adversarial test strengthening

This is an isolated experimental research record, **not** vehicle driving assistance or a calibrated collision-probability claim.

## Verified

- On designated desktop DO, new isolated Python **stdlib unittest** module `scripts/behavior_v3_v4/test_adversarial_unittest.py` was executed successfully: **16/16 PASS**. A previous first-run test case used an incorrect rear-distance expectation; after correcting the test fixture, 16/16 passed. No core V3 or frozen RiskFrame v1 production code was edited.
- Execution command: `python -m unittest scripts.behavior_v3_v4.test_adversarial_unittest -v`.
- Local evidence: `artifacts/overnight_rdc_main/v4_adversarial_unittest_20261111_1301.log`; SHA256 `E4A262AA138AFC6AA8D766584105BFE8CE7FF27FAC181AB0AE67AEE0FF86D032`.
- Coverage: signal-only without movement, unavailable neighboring signal provenance, two-direction no-signal cut-in, aborted preparation, fast rear approach and TTC, observed vs CV-projected overlap, synchronized and unsynchronized neighbors, multi-track order, identity epoch resets, future/delayed frames, malformed dimensions, one-to-one event matching and embargoed grouped holdouts.
- Previous V3 72/72 and physical-risk 35/35 checks are **prior** independently logged runs, not newly executed in this change.

## Four roles and ownership

- **RDC (65% work priority)**: low-memory data/QC verification only. Local prompt `ops/coordination_20261111_1300/RDC_MAIN_QA.md`.
- **Codex CLI (20%)**: only independent V3/V4 new implementation and stdlib tests; no edits to V3 original, PRISM, or frozen v1. Prompt `ops/coordination_20261111_1300/CODEX_CLI_PROMPT.txt`.
- **Hermes (10%)**: read-only audit of 20 falsifiable counterexamples, no file edits. Prompt `ops/coordination_20261111_1300/HERMES_READ_ONLY_PROMPT.txt`.
- **ChatGPT (5%)**: independent official-source/license review, progress verification and reporting. Prompt `ops/coordination_20261111_1300/GPT_CHAT_COORDINATION.md`.

## Execution state and safety

- Windows local scheduled task `RiskRadar_Engine02_Adversarial_20261111` was registered on DO, 30-minute cadence from 13:30 to 17:00 KST on November 11 only. It invokes Codex/Hermes serially through previously installed CLI wrappers only if RAM >=2.3GiB, CPU <65%, disk >=12GiB and fewer than 3 other running codex/hermes processes. Otherwise it logs DEFERRED, without starting any CLI.
- First immediate attempt at 13:12:58 KST: **DEFERRED_RESOURCES_OR_AGENTS**, RAM 1.63GiB, disk 26.23GiB, CPU 11%, 9 existing codex/hermes processes. Existing processes do **not** demonstrate that either role was already working on this project.
- A separate ChatGPT hourly check-in was enabled from 13:30 KST for 4 occurrences, without claiming that schedule setup itself executes desktop CLI.
- No new datasets downloaded, no raw CARLA/NGSIM CSV uploaded, no main merge/force push, no access to notebook or FORM NEXT.
- Real held-out trajectory ADE/FDE, intent recall/precision, lead time, false alerts per hour: **NOT MEASURED**; no real-world safety validated.

## Git backup

- Personal repo: `Ukdongs/Practice`, isolated branch `feature/engine02-research-snapshot-20261111`.
- Initial 27-file remote backup verified under commit `4bc0c554c8a9f341fec4b830d113742f3b21e50c`. The new unittest was independently added in commit `25cffae2d74b5d45ee8a0bea060cd8dfa21762e0`.
- Excludes restricted datasets, credentials, protected team source, heavyweight models and original recordings.
