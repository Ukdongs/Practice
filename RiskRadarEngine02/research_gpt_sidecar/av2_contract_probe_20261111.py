"""Research-only AV2 observation guard with synthetic stdlib tests.

NON-PRODUCTION research sidecar: no AV2 dataset imports or downloads,
no model weights, no RiskFrame v1 or PRISM integration, no safety claim.

Status at authoring: NOT EXECUTED (authorized DO device offline).
To verify later on DO:
    python av2_contract_probe_20261111.py -v

AV2 ObjectState has XY box-center position, heading, velocity, timestep,
observed. Dataset metadata supplies timestamps_ns and track/scenario IDs.
Turn indicators and road-relative s/d are NOT present in this schema.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import unittest


@dataclass(frozen=True)
class AV2Input:
    # recording_id is an EXTERNAL provenance field, not an ObjectState field.
    recording_id: str
    scenario_id: str
    track_id: str
    timestep: int
    as_of_timestep: int
    timestamps_ns: tuple[int, ...]
    observed: bool
    category: str
    center_xy_m: tuple[float, float]
    heading_rad: float
    velocity_xy_mps: tuple[float, float]
    # AV2 ObjectState does NOT provide these dimensions. A verified external
    # source is required before performing vehicle-origin conversion.
    verified_length_m: float | None = None
    # An independently validated HD-map conversion may supply these fields.
    verified_road_s_m: float | None = None
    verified_road_d_m: float | None = None
    lane_reference: str = ""
    lane_geometry_reliable: bool = False


@dataclass(frozen=True)
class GateResult:
    status: str
    reason: str
    actor_key: tuple[str, str, str] | None = None
    elapsed_s: float | None = None
    front_center_xy_m: tuple[float, float] | None = None
    road_s_m: float | None = None
    road_d_m: float | None = None
    indicator: str = "UNKNOWN"
    indicator_provenance: str = "UNKNOWN"
    ground_truth_maneuver: str | None = None
    eligible_for_inference: bool = False


def _finite(*vals: float) -> bool:
    return all(
        isinstance(x, (float, int)) and not isinstance(x, bool)
        and math.isfinite(x) for x in vals
    )


def _int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def gate(frame: AV2Input) -> GateResult:
    """Fail closed on unsupervised, future, unmapped or dimensionless records.

    Only validates a *caller-provided* road-frame conversion, never fabricates
    a map transformation. Does not assert that the caller's labels are true.
    """
    blocked = lambda why: GateResult(status="BLOCKED", reason=why)
    if not all(
        isinstance(s, str) and bool(s.strip())
        for s in (frame.recording_id, frame.scenario_id, frame.track_id)
    ):
        return blocked("MISSING_COMPOSITE_ID")
    if (
        not _int(frame.timestep) or not _int(frame.as_of_timestep)
        or frame.timestep < 0 or frame.as_of_timestep < 0
        or frame.timestep > frame.as_of_timestep
    ):
        return blocked("FUTURE_OR_INVALID_TIMESTEP")
    if frame.observed is not True:
        return blocked("UNOBSERVED_OR_INVALID_VISIBILITY")
    stamps = frame.timestamps_ns
    if not isinstance(stamps, (tuple, list)) or len(stamps) <= frame.as_of_timestep:
        return blocked("MISSING_TIMESTAMP")
    # Future timestamps in the file must not affect causal validation.
    prefix = stamps[: frame.as_of_timestep + 1]
    if not all(_int(t) and t >= 0 for t in prefix):
        return blocked("INVALID_TIMESTAMP")
    if not all(b > a for a, b in zip(prefix, prefix[1:])):
        return blocked("NONMONOTONIC_TIMESTAMP")
    if (
        not isinstance(frame.center_xy_m, tuple)
        or len(frame.center_xy_m) != 2
        or not isinstance(frame.velocity_xy_mps, tuple)
        or len(frame.velocity_xy_mps) != 2
        or not _finite(
            *frame.center_xy_m, frame.heading_rad, *frame.velocity_xy_mps
        )
    ):
        return blocked("INVALID_MAP_FRAME_KINEMATICS")
    if not _finite(frame.verified_length_m or float("nan")):
        return blocked("UNVERIFIED_VEHICLE_LENGTH")
    if not (0.5 <= frame.verified_length_m <= 30.0):
        return blocked("INVALID_VEHICLE_LENGTH")
    if (
        frame.lane_geometry_reliable is not True
        or not isinstance(frame.lane_reference, str)
        or not frame.lane_reference.strip()
        or not _finite(frame.verified_road_s_m, frame.verified_road_d_m)
    ):
        return blocked("UNVERIFIED_ROAD_GEOMETRY")
    # AV2 heading is map-frame; this origin transform is valid only if
    # externally verified_length_m is available, not from ObjectState alone.
    half = frame.verified_length_m / 2
    front_xy = (
        frame.center_xy_m[0] + half * math.cos(frame.heading_rad),
        frame.center_xy_m[1] + half * math.sin(frame.heading_rad),
    )
    # All time operations use integer nanoseconds before converting to seconds.
    elapsed_s = (prefix[frame.timestep] - prefix[0]) / 1_000_000_000.0
    return GateResult(
        status="PASS",
        reason="VERIFIED_INPUT_CONTRACT_ONLY",
        actor_key=(frame.recording_id, frame.scenario_id, frame.track_id),
        elapsed_s=elapsed_s,
        front_center_xy_m=front_xy,
        road_s_m=frame.verified_road_s_m,
        road_d_m=frame.verified_road_d_m,
        # The official AV2 ObjectState has no signal or maneuver-label field.
        indicator="UNKNOWN",
        indicator_provenance="UNKNOWN",
        ground_truth_maneuver=None,
        eligible_for_inference=True,
    )


def fixture(**changes: object) -> AV2Input:
    data = dict(
        recording_id="recording-A", scenario_id="scenario-A",
        track_id="actor-7", timestep=1, as_of_timestep=1,
        timestamps_ns=(0, 100_000_000, 200_000_000),
        observed=True, category="FOCAL_TRACK",
        center_xy_m=(10.0, 5.0), heading_rad=0.0,
        velocity_xy_mps=(10.0, 0.0),
        verified_length_m=4.0,
        verified_road_s_m=10.0, verified_road_d_m=0.0,
        lane_reference="verified-roadframe", lane_geometry_reliable=True,
    )
    data.update(changes)
    return AV2Input(**data)


class TestAV2ConservativeContract(unittest.TestCase):
    def test_composite_identity_not_only_track_id(self):
        a = gate(fixture())
        b = gate(fixture(scenario_id="scenario-B"))
        c = gate(fixture(recording_id="recording-B"))
        self.assertEqual((a.status, b.status, c.status), ("PASS",) * 3)
        self.assertNotEqual(a.actor_key, b.actor_key)
        self.assertNotEqual(a.actor_key, c.actor_key)

    def test_nanoseconds_not_timestep_as_ms(self):
        result = gate(fixture())
        self.assertEqual(result.status, "PASS")
        self.assertAlmostEqual(result.elapsed_s, 0.1)

    def test_scoring_category_is_not_maneuver_truth(self):
        for category in ("FOCAL_TRACK", "SCORED_TRACK", "TRACK_FRAGMENT"):
            with self.subTest(category=category):
                result = gate(fixture(category=category))
                self.assertEqual(result.status, "PASS")
                self.assertIsNone(result.ground_truth_maneuver)

    def test_box_center_to_front_center_verified_length(self):
        r = gate(fixture(center_xy_m=(10., 5.), heading_rad=0.))
        self.assertEqual(r.front_center_xy_m, (12., 5.))
        q = gate(fixture(center_xy_m=(10., 5.),
                         heading_rad=math.pi / 2))
        self.assertAlmostEqual(q.front_center_xy_m[0], 10.)
        self.assertAlmostEqual(q.front_center_xy_m[1], 7.)

    def test_no_externally_verified_length_fails_closed(self):
        self.assertEqual(
            gate(fixture(verified_length_m=None)).reason,
            "UNVERIFIED_VEHICLE_LENGTH",
        )

    def test_unobserved_future_track_state_is_never_input(self):
        self.assertEqual(
            gate(fixture(observed=False)).reason,
            "UNOBSERVED_OR_INVALID_VISIBILITY",
        )
        self.assertEqual(
            gate(fixture(timestep=2, as_of_timestep=1)).reason,
            "FUTURE_OR_INVALID_TIMESTEP",
        )

    def test_missing_signals_stay_unknown_not_off(self):
        r = gate(fixture(category="FOCAL_TRACK"))
        self.assertEqual(r.status, "PASS")
        self.assertEqual(r.indicator, "UNKNOWN")
        self.assertEqual(r.indicator_provenance, "UNKNOWN")
        self.assertIsNone(r.ground_truth_maneuver)

    def test_no_map_alignment_no_inference(self):
        for change in (
            {"lane_geometry_reliable": False},
            {"lane_reference": ""},
            {"verified_road_s_m": None},
            {"verified_road_d_m": None},
        ):
            with self.subTest(change=change):
                r = gate(fixture(**change))
                self.assertEqual(r.status, "BLOCKED")
                self.assertFalse(r.eligible_for_inference)

    def test_future_timestamp_contents_do_not_change_past_output(self):
        a = gate(fixture(timestamps_ns=(0, 100_000_000, 200_000_000)))
        b = gate(fixture(timestamps_ns=(0, 100_000_000, -999_999_999)))
        self.assertEqual(a, b)
        self.assertEqual(a.status, "PASS")

    def test_nonmonotonic_prefix_timestamp_blocked(self):
        self.assertEqual(
            gate(fixture(timestamps_ns=(100_000_000, 100_000_000))),
            GateResult(status="BLOCKED", reason="NONMONOTONIC_TIMESTAMP"),
        )

    def test_invalid_geometry_and_nonfinite_values_blocked(self):
        self.assertEqual(
            gate(fixture(center_xy_m=(float("nan"), 2.))).status, "BLOCKED"
        )
        self.assertEqual(
            gate(fixture(verified_length_m=-1.)).status, "BLOCKED"
        )

    def test_missing_composite_identity_blocked(self):
        self.assertEqual(
            gate(fixture(recording_id="")).reason, "MISSING_COMPOSITE_ID"
        )

    def test_cannot_claim_real_safety_metric(self):
        r = gate(fixture())
        self.assertFalse(hasattr(r, "collision_probability"))
        self.assertFalse(hasattr(r, "precision"))
        self.assertEqual(r.reason, "VERIFIED_INPUT_CONTRACT_ONLY")


if __name__ == "__main__":
    unittest.main()
