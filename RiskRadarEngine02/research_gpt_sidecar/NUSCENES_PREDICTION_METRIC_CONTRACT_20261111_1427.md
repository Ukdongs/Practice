# Engine02 independent metric contract audit: nuScenes prediction benchmark

**Checked:** 2026-11-11 14:27 KST. **Scope:** public official metric definitions only. DO device `ab05bb36-afc0-431f-9bdc-2c96a4db8c22` was **offline** (last seen approximately one hour earlier). No DO RAM/CPU/disk, scheduler, agent outputs or exit codes were accessible; no local code or dataset was run. Notebook, FORM NEXT, PRISM originals, and frozen RiskFrame v1 were not accessed.

## One new finding

The official nuScenes prediction README defines 6-second prediction at 2 Hz, hence **12 future XY samples**, with predictions in the **global frame**. The task allows up to 25 modes, each with a probability, and up to 2 seconds of past agent history. Evaluation reports minADE_k, minFDE_k and MissRate_2_k. Importantly, the official **MissRate_2_k is a maximum-over-horizon displacement criterion**, not simply endpoint FDE >2m: a mode is missed if **any** future point is more than 2m from ground truth; a top-k prediction is a miss when no top-k mode avoids that condition. The official implementation describes the metric as a maximum pointwise tolerance test.

**Adversarial counterexample for a future unit test (NOT EXECUTED):**
- 12 ground-truth points all (0,0) m; a single forecast mode with (3,0) m at sample 6 and (0,0) m for the other 11.
- Endpoint FDE = 0m, but max pointwise error = 3m. Under nuScenes 2m MissRate the forecast is a **MISS**, while an endpoint-only implementation incorrectly counts a HIT.
- For a 12-sample single mode, ADE = 3/12 = 0.25m; FDE = 0m; miss = 1. These are **synthetic hand-calculated assertions**, NOT measured model performance.
- Counterexample for mode selection: add a second lower-probability mode with max pointwise error 1m. At k=1 the example remains MISS if the 3m-spike mode has the higher probability; at k=2 it becomes HIT. Evaluate modes by probability ranking and report k, rather than silently evaluating all modes.

## Evaluation contract required before Engine02 can claim metrics

1. Fix dataset and version, official challenge split, per-agent/per-scenario IDs, map frame, observation horizon, prediction horizon and sample frequency. Do not pool 10Hz AV2 with 2Hz nuScenes samples without explicit resampling.
2. Keep evaluation method/dataset metric names distinct: `nuscenes_missrate_maxpoint_2m@k` is **not** interchangeable with endpoint-based miss definitions used by other challenges. Do not report generic 'miss rate' without protocol.
3. Report minADE_k/minFDE_k alongside K, trajectory probabilities, valid sample count, scenario counts, and selection/aggregation policy. Compare like-for-like horizons and coordinate frames only.
4. Intent precision/recall requires separately observed maneuver/indicator ground truth, threshold and event definition. False alerts/hour requires independent event matching and a valid exposure-hours denominator; lead time requires time-stamped event onset. None is supplied by a displacement-only challenge metric.
5. **No real driving ADE/FDE, intent precision/recall, lead time, or false alerts/hour was measured in this run.** All remain `NOT MEASURED`. This benchmark is not proof of real vehicle safety.

## Official references

- nuScenes prediction README, task setup and metrics: https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/eval/prediction/README.md
- Official metric implementation, `MissRateTopK`: https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/eval/prediction/metrics.py

## Handoff

- Public-source metric definition and synthetic counterexample **PASS (documentary audit only)**.
- DO resource check / scheduler / Codex / Hermes **BLOCKED (device offline)**.
- Synthetic test execution **NOT RUN**.
- Any empirical road prediction metric **NOT MEASURED**.
- No production code edits, no raw data download or Git upload. This text is restricted to `research_gpt_sidecar`.
