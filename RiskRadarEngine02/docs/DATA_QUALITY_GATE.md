# Historical NGSIM input quality gate

This is QA of publicly recorded historical trajectories, not a train/test split,
predictive accuracy certification, or evidence of real-world safety. These data
MUST NOT cause on-road alerts. No application-facing schema, vehicle behavior,
simulation V2 file, or engine implementation is changed.

## Files and execution

- `scripts/data_quality/analyze_ngsim.py`: independently runnable Python 3.9+
  standard-library analyzer; no downloads, network calls, or engine imports.
- `scripts/data_quality/run_local.ps1`: optional four-window reproduction runner.
- `prism-risk-engine/tests/test_data_quality.py`: isolated pytest tests.
- This document.

From the repository root, with an available Python interpreter:

```powershell
python scripts/data_quality/analyze_ngsim.py C:\Users\Public\Documents\RiskRadarOpenDataResearch\ngsim_contiguous_i80_20s.csv --output artifacts/data_quality/i80_20s.json
python -m pytest prism-risk-engine/tests/test_data_quality.py -q -p no:cacheprovider --basetemp=artifacts/data_quality/pytest_tmp
```

The actual offline reproduction in this environment used:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/data_quality/run_local.ps1 -Python 'C:\Program Files\LibreOffice\program\python.exe' -PytestSitePackages 'C:\Users\Public\Documents\RiskRadarOpenDataResearch\.venv\Lib\site-packages'
```

The process-scoped PowerShell execution option does not change system settings.
Python 3.13.15 and locally installed pytest 8.4.2 were used. The research virtual
environment's launcher is unusable here; its pure Python pytest packages were
read via PYTHONPATH with bytecode writes disabled. No dependencies were installed.
The analyzer itself needs no pytest. All source CSV access is read-only.

`artifacts/` is already gitignored. CLI report destinations must resolve inside
this repository's artifacts directory. `artifacts/data_quality/run.log` records
interpreter, timestamp, input paths, commands, aggregate results and pytest output;
the four JSON reports contain input SHA-256 hashes. Reports contain only aggregate
counts and at most 20 quarantine references, not copied source rows. Temporary
SQLite files use the system temporary directory and are closed and removed.

## Validation and interpretation

Headers are required exactly as lower-case NGSIM fields: location, vehicle_id,
global_time, local_x, local_y, v_length, v_width, v_vel, v_acc. Duplicate headers
are rejected. Blank/non-integer identities and timestamps, malformed row widths,
nonfinite/missing coordinates, dimensions, speed and acceleration are flagged.
IDs are positive signed 64-bit integers; time is a nonnegative signed 64-bit
integer in milliseconds. Empty files with valid headers report zero observations,
never successful safety validation.

All spatial quantities use the exact conversion 1 ft = 0.3048 m. Review thresholds
are length 0.5?30 m, width 0.3?5 m, speed 0?70 m/s, and acceleration magnitude
at most 15 m/s2. These are broad QA heuristics, not certified physical limits.
Passing thresholds cannot establish accurate annotation.

Track keys are (location, vehicle_id); duplicate keys include the exact timestamp.
Uniqueness checks use all preceding records, not just the last record. Monotonicity
compares each arrival to the track's previous maximum timestamp; repeated times
count as both duplicates and nonmonotonic observations. Counts are overlapping
diagnostics, not distinct defective-row totals. This requires time-ordered input
per track; it does not silently sort or repair unordered recordings.

For a new high-water timestamp exactly 100 ms after the previous one, with finite
coordinates and speeds at both endpoints, compute Euclidean displacement / 0.1 s
and compare against mean endpoint reported speed. Absolute residual buckets are
<=1, >1 to <=3, >3 to <=5 and >5 m/s; mean, maximum, and comparison count accompany
the histogram. Residual >5 m/s is a quarantine candidate. Displacement >10 m per
100 ms is a teleport/ID mismatch candidate, never a proven identity error. No
reported velocity is treated as ground truth. Site-specific axis signs/rotations
do not change displacement magnitude. Coordinate changes due to vehicle rotation,
annotation noise, differing reference conventions, and genuine turns still limit
interpretation. Invalid coordinate rows break comparisons across those rows.

Gaps greater than 100 ms are flagged; integer multiples of 100 ms give candidate
internal missing-record counts. Off-cadence intervals are flagged separately.
Track beginnings/endings and vehicles entering/leaving the sample are not missing
records. `counts.missing_records_inferred` is an arrival-order **candidate** count;
use `missing_records_assessment.count` for the qualified result. When timestamps
are nonmonotonic, off cadence, or invalid, that assessment is `not evaluated` with
a null count: later rows may fill apparent gaps. No global completeness claim is
possible from a window alone.

SQLite stores exact seen keys and one small state per track on disk, with a 2 MiB
page-cache target. Python retains one CSV row, a fixed histogram and at most 20
examples; memory does not grow with row or track count. Temporary disk use grows
with distinct vehicle/time keys. Hashing is a separate bounded-memory read pass;
inputs should remain unchanged throughout a run.

## Geometry and false certainty guard

`local_x/local_y` identify a recorded vehicle reference point. They are **not a
validated rectangle center**. The precise source-specific reference-point
convention and its center offset require independent verification. Neither a
velocity-derived direction nor a lane identifier validates body heading,
particularly at intersections, turns and stops.

These CSV inputs do not validate both heading geometry and center semantics.
Consequently all-pairs oriented-rectangle comparisons are **not evaluated**, with
`overlap_count: null`. There is deliberately no override to label geometry as
validated, no fabricated zero collisions, and no interpolation between records.
A future geometry evaluator would require a separately validated source adapter
and compare every pair at each common recorded timestamp only. This analyzer does
not provide that adapter or claim collision/safety certification.

## Offline observed results

18 isolated pytest cases passed. Coverage includes valid rows, feet conversion
through residual calculations, repeated/reversed/nonadjacent duplicate timestamps,
speed discrepancies, teleport candidates, blank/nonfinite coordinates, bad
dimensions, header rejection, invalid identity/speed/acceleration, site axes,
internal gaps, empty input and the false-certainty guard.

Each source window spans exactly 20,000 ms (inclusive endpoint observations).

| Window | Rows | Vehicles by location/ID | Compared 100 ms intervals | Residual >5 m/s | Duplicate keys | Nonmonotonic | Teleport/ID candidates |
|---|---:|---:|---:|---:|---:|---:|---:|
| i-80 | 27,910 | 185 | 27,725 | 10 | 0 | 0 | 0 |
| us-101 | 23,433 | 164 | 23,269 | 0 | 0 | 0 | 0 |
| lankershim | 10,815 | 71 | 10,744 | 9 | 0 | 0 | 0 |
| peachtree | 17,757 | 107 | 116 | 7 | 1,380 | 17,152 | 6 |

All four windows had zero bad-dimension flags and no invalid-field flags. The
first three had no inferred internal gaps. Peachtree had 382 arrival-order gap
events, representing 8,109 candidate missing records; **actual missing records
are not evaluated** because of ordering violations. Its comparison coverage is
particularly limited. Quarantine Peachtree for ordering/identity review before
any further use; review residual candidate intervals in the other windows.
The current tool reports diagnostics and does not rewrite, sort, deduplicate,
or automatically accept any recording. CLI exit 0 means report creation only;
exit 2 indicates an input/header/output error. Consumers must inspect diagnostics,
coverage and unresolved assessments; there is no overall safety-pass flag.

## Source, provenance and license are separate reviews

Inputs are the user-provided local sampled government NGSIM windows under
`C:\Users\Public\Documents\RiskRadarOpenDataResearch`. The local
`contiguous_windows_manifest.json` describes the transportation.gov NGSIM resource
`8ect-6jqj`, query ranges, row counts and hashes. This manifest was read locally;
neither its claims nor current upstream terms were checked over the network.
The i-80 hash matched the local manifest. Each report records its own input hash
for reproduction; a hash alone proves neither provenance nor licensing.

Provenance review must separately verify origin, extraction query, site/time
conventions, identity scope, units, coordinate reference point and transformations.
License review must separately verify reuse/redistribution terms and attribution.
Public accessibility and government hosting do not themselves authorize every
reuse. Historical NGSIM annotations may contain tracking/annotation errors;
residual and overlap candidates are not established real-world physical events.
No raw source data was copied into this repository or committed. No network,
bulk download, research-folder write, commit or push was performed.
