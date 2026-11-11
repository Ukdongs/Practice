"""Engine02 additional adversarial research checks (stdlib-only).
No real-world safety/performance claim. Does not touch frozen RiskFrame v1.
Run: python -m unittest scripts.behavior_v3_v4.test_adversarial_unittest -v
"""
import unittest

from scripts.behavior_v3 import IntentEngine, Observation, Neighbor
from scripts.behavior_v3.evaluation import Event, Window, event_metrics, validate_holdout


def obs(t, track="target", **changes):
    values = dict(d_m=0., s_m=t * .02, vd_mps=0., vs_mps=20.)
    values.update(changes)
    return Observation(track, t, **values)


def warmed(**kwargs):
    engine = IntentEngine()
    engine.observe(obs(0, **kwargs), now_ms=0)
    return engine, engine.observe(obs(100, **kwargs), now_ms=100)


class AdversarialBehaviorV4(unittest.TestCase):
    def test_signals_without_motion_not_change(self):
        for direction in ("LEFT", "RIGHT"):
            with self.subTest(direction=direction):
                _, r = warmed(indicator=direction, indicator_provenance="OBSERVED")
                self.assertEqual(r.motion_intention, "PREPARE_" + direction)
                self.assertEqual(r.features["lateral_velocity_mps"], 0.)

    def test_other_vehicle_signal_not_inferred_from_ego(self):
        for prov in ("EGO_OTHER_TRACK", "INFERRED", "UNKNOWN"):
            with self.subTest(prov=prov):
                _, r = warmed(indicator="LEFT", indicator_provenance=prov)
                self.assertEqual(r.features["indicator"], "UNKNOWN")
                self.assertEqual(r.motion_intention, "KEEP")
                self.assertIn("indicator_unobserved", r.uncertainty)

    def test_no_signal_fast_lateral_cutin(self):
        for direction, v in (("LEFT", -.8), ("RIGHT", .8)):
            with self.subTest(direction=direction):
                engine = IntentEngine()
                engine.observe(obs(0, vd_mps=v), now_ms=0)
                r = engine.observe(obs(100, d_m=v*.1, vd_mps=v), now_ms=100)
                self.assertEqual(r.motion_intention, "CHANGE_" + direction)
                self.assertEqual(r.features["indicator"], "UNKNOWN")
                self.assertTrue(r.research_only)

    def test_aborted_prepare_is_not_completed_change(self):
        engine = IntentEngine()
        engine.observe(obs(0, d_m=-.2, vd_mps=-.4), now_ms=0)
        a = engine.observe(obs(100, d_m=-.24, vd_mps=-.4), now_ms=100)
        b = engine.observe(obs(200, d_m=-.24, vd_mps=.4), now_ms=200)
        self.assertEqual(a.motion_intention, "PREPARE_LEFT")
        self.assertEqual(b.motion_intention, "ABORT_LEFT")
        self.assertEqual(b.risk_geometry["observed_body_overlap_ids"], [])

    def test_adjacent_rear_fast_ttc_not_body_collision(self):
        engine = IntentEngine()
        engine.observe(obs(0), now_ms=0)
        rear = Neighbor("rear", 100, 3.6, -18, 0, 38)
        r = engine.observe(obs(100, neighbors=(rear,)), now_ms=100)
        self.assertEqual(r.motion_intention, "KEEP")
        self.assertEqual(r.risk_geometry["observed_body_overlap_ids"], [])
        gap = r.risk_geometry["neighbor_gaps"][0]
        self.assertEqual(gap["side"], "RIGHT")
        self.assertEqual(gap["position"], "REAR")
        self.assertAlmostEqual(gap["longitudinal_ttc_s"], (20-4.6)/18)  # ego s=2m at t=100ms

    def test_future_projection_not_observed_collision(self):
        engine = IntentEngine()
        engine.observe(obs(0), now_ms=0)
        rear = Neighbor("closing", 100, 0, -18, 0, 35)
        r = engine.observe(obs(100, neighbors=(rear,)), now_ms=100)
        self.assertEqual(r.risk_geometry["observed_body_overlap_ids"], [])
        self.assertTrue(any(x["track_id"] == "closing" for x in r.risk_geometry["cv_projected_overlap"]))
        self.assertIn("no collision probability", r.risk_geometry["semantics"])

    def test_mixed_invalid_and_valid_neighbors_preserves_valid(self):
        engine = IntentEngine()
        engine.observe(obs(0), now_ms=0)
        stale = Neighbor("stale", 0, 0, 0, 0, 20)
        good = Neighbor("fresh", 100, 3.6, 6, 0, 17)
        r = engine.observe(obs(100, neighbors=(stale, good)), now_ms=100)
        self.assertEqual([n["track_id"] for n in r.risk_geometry["neighbor_gaps"]], ["fresh"])
        self.assertIn("invalid_or_unsynchronized_neighbors_omitted", r.uncertainty)

    def test_simultaneous_track_input_order_invariant(self):
        def run(order):
            engine = IntentEngine()
            results = {}
            for t in (0, 100):
                for tid in order:
                    results[(tid, t)] = engine.observe(obs(t, track=tid), now_ms=t).motion_intention
            return results
        self.assertEqual(run(("A", "B")), run(("B", "A")))

    def test_epoch_reset_requires_new_warmup(self):
        engine = IntentEngine()
        engine.observe(obs(0, d_m=-.2, vd_mps=-.4), now_ms=0)
        engine.observe(obs(100, d_m=-.24, vd_mps=-.4), now_ms=100)
        r = engine.observe(obs(200, identity_epoch="next"), now_ms=200)
        self.assertEqual(r.motion_intention, "UNKNOWN")
        self.assertEqual(r.reasons, ("identity_or_lane_reference_reset",))
        self.assertEqual(engine.observe(obs(300, identity_epoch="next"), now_ms=300).motion_intention, "KEEP")

    def test_future_and_too_short_frame_do_not_poison_history(self):
        engine = IntentEngine()
        self.assertEqual(engine.observe(obs(100), now_ms=0).motion_intention, "UNKNOWN")
        self.assertEqual(engine.observe(obs(0), now_ms=0).motion_intention, "UNKNOWN")
        self.assertIn("sampling_interval_too_short", engine.observe(obs(1), now_ms=1).reasons)
        r = engine.observe(obs(100), now_ms=100)
        self.assertEqual(r.motion_intention, "KEEP")
        self.assertAlmostEqual(r.features["track_age_s"], .1)

    def test_invalid_neighbor_dimensions_rejected(self):
        engine = IntentEngine()
        engine.observe(obs(0), now_ms=0)
        bad = Neighbor("invalid", 100, 0, 0, 0, 20, length_m=100)
        r = engine.observe(obs(100, neighbors=(bad,)), now_ms=100)
        self.assertEqual(r.risk_geometry["observed_body_overlap_ids"], [])
        self.assertIn("invalid_or_unsynchronized_neighbors_omitted", r.uncertainty)

    def test_earliest_matching_alert_on_boundary(self):
        r = event_metrics([Event("A", "LEFT", 2000), Event("A", "LEFT", 2200)],
                          [Event("A", "LEFT", 5000)], exposure_track_hours=1, lead_window_ms=3000)
        self.assertEqual(r["true_positive_events"], 1)
        self.assertEqual(r["lead_time_s"], [3.0])
        self.assertEqual(r["false_alert_episodes"], 1)

    def test_one_alert_not_two_ground_truth_events(self):
        r = event_metrics([Event("A", "LEFT", 2500)],
                          [Event("A", "LEFT", 3000), Event("A", "LEFT", 3100)],
                          exposure_track_hours=1)
        self.assertEqual(r["true_positive_events"], 1)
        self.assertEqual(r["missed_events"], 1)

    def test_same_recording_embargo_boundary_is_enforced(self):
        a = Window("site", "recording", "driver1", 0, 1000, "train")
        b = Window("site", "recording", "driver2", 1500, 2000, "train")
        with self.assertRaises(ValueError):
            validate_holdout([a, b], embargo_ms=501)
        self.assertEqual(validate_holdout([a, b], embargo_ms=500)["status"], "PASS")

    def test_unknown_driver_blocks_holdout(self):
        with self.assertRaises(ValueError):
            validate_holdout([Window("s", "r", "UNKNOWN", 0, 1000, "test")])

    def test_bad_body_measurement_resets_track(self):
        engine, _ = warmed()
        invalid = engine.observe(obs(200, width_m=40), now_ms=200)
        self.assertEqual(invalid.motion_intention, "UNKNOWN")
        self.assertEqual(engine.observe(obs(300), now_ms=300).motion_intention, "UNKNOWN")
        self.assertEqual(engine.observe(obs(400), now_ms=400).motion_intention, "KEEP")


if __name__ == "__main__":
    unittest.main()
