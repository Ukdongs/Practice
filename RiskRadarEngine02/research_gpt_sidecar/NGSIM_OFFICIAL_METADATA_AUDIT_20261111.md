# Engine02 GPT sidecar — official NGSIM Peachtree provenance and license gate

Date: 2026-11-11 KST
Status: PARTIAL (official metadata review PASS; local DO data/provenance and independent model metrics BLOCKED)

## One independent finding
The U.S. DOT/FHWA Peachtree metadata explicitly warns that TXT is the original trajectory representation while CSV is converted, advises using TXT to ensure proper data, reports no completed attribute-accuracy assessment, and makes no completeness guarantee. Therefore the existing Peachtree QUARANTINE must remain in force. Any duplicate (site, recording, vehicle, frame/time) keys, TXT/CSV disagreement, discontinuities, or metadata unit/reference mismatches must be investigated before training, test-split eligibility, or claims of independent validation. This is a documentary gate, not a newly executed dataset validation.

## Source evidence (official only)
1. USDOT FHWA, Peachtree Street Metadata Documentation (original attached PDF):
https://data.transportation.gov/api/views/8ect-6jqj/files/8b5a833b-e286-467f-8c55-af45be37c8ab?download=true&filename=4-+Peachtree+Street+Metadata+Documentation.pdf
2. USDOT ITS JPO, NGSIM Vehicle Trajectories and Supporting Data, official portal (metadata updated 2026-11-02; data last updated 2018-08-27):
https://data.transportation.gov/Automobiles/Next-Generation-Simulation-NGSIM-Vehicle-Trajector/8ect-6jqj/data
3. data.gov catalog record (metadata modified 2026-11-02) lists license CC BY-SA 3.0 and public access:
https://catalog.data.gov/dataset/next-generation-simulation-ngsim-vehicle-trajectories-and-supporting-data

## Licensing boundary
The dataset catalog metadata lists CC BY-SA 3.0. That does NOT automatically license separately obtained simulator code, downstream model weights, third-party assets or all derivative software under the same terms. Independently review attribution/share-alike applicability and each artifact's provenance before redistribution. This sidecar does not reproduce or upload any raw NGSIM data.

## Model-evaluation boundary
ADE/FDE, intent precision/recall, event lead-time and false alerts per track-hour: NOT MEASURED (no eligible independently verified held-out evaluation was executed). Use disjoint site/time/recording/driver groups, document identity continuity, leakage prevention and labels before calculating these metrics. Do not treat 10 Hz frame frequency as a guarantee of measurement accuracy.

## Execution provenance
At 2026-11-11 13:29 KST, local-time source confirmed the pre-17:00 window. RDC reported DO online in a stale listing (last seen 14 minutes earlier), but a DO-only read-only PowerShell status probe timed out. Subsequent DO session/process requests explicitly returned no currently online Desktop Commander device. Thus DO RAM/CPU/disk, coordination events, Codex/Hermes exit codes and current Windows scheduled-task outcome were NOT VERIFIED. No new CLI sessions, local tests, downloads, main merges or force pushes were initiated. Historical 72/72 V3, 35/35 physics and 16/16 stdlib are NOT rerun or independently verified this run.

Gate: PARTIAL for one official documentary finding; BLOCKED for DO-local validation and any production readiness.
