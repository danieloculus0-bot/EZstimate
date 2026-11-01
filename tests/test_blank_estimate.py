"""Synthetic evidence for flat-first individual-part material estimate."""
import unittest

from ezstimate.blank_estimate import estimate_component_blank
from ezstimate.server import app


class BlankEstimateTests(unittest.TestCase):
    def test_supplied_flat_pattern_preferred_without_extra_allowance(self):
        result = estimate_component_blank({
            "scope": "individual_component", "basis": "flat_pattern",
            "flat_length_in": "10", "flat_width_in": "4",
            "k_factor": "0.44", "cushion_in": "0.030",
            "material_price_per_sq_in": "2.50",
        })
        self.assertEqual(result["length_in"], "10.0000")
        self.assertEqual(result["width_in"], "4.0000")
        self.assertEqual(result["material_area_sq_in"], "40.0000")
        self.assertEqual(result["material_cost_each"], "100.00")
        self.assertIsNone(result["k_factor"])
        self.assertEqual(result["cushion_in"], "0")
        self.assertFalse(result["approved"])

    def test_true_flat_area_beats_bounding_box(self):
        result = estimate_component_blank({
            "scope": "individual_component", "basis": "flat_pattern",
            "flat_length_in": "10", "flat_width_in": "4",
            "flat_area_sq_in": "30", "material_price_per_sq_in": "2",
        })
        self.assertEqual(result["material_area_sq_in"], "30.0000")
        self.assertEqual(result["bounding_box_area_sq_in"], "40.0000")
        self.assertEqual(result["material_cost_each"], "60.00")

    def test_k_factor_fallback_has_one_cushion_each_dimension(self):
        result = estimate_component_blank({
            "scope": "individual_component", "basis": "k_factor_approximation",
            "outside_leg_sum_in": "8", "blank_width_in": "4",
            "thickness_in": ".125", "inside_radius_in": ".125",
            "bend_angle_deg": "90", "bend_count": "2",
            "material_price_per_sq_in": "2",
        })
        self.assertEqual(result["k_factor"], "0.44")
        self.assertEqual(result["cushion_in"], "0.030")
        self.assertEqual(result["width_in"], "4.0300")
        self.assertAlmostEqual(float(result["length_in"]), 7.5955, places=3)
        self.assertGreater(float(result["material_area_sq_in"]), 30)
        self.assertEqual(result["status"], "draft_review")
        self.assertTrue(result["needs_review"])

    def test_missing_cost_stays_unknown(self):
        result = estimate_component_blank({
            "scope": "individual_component", "basis": "flat_pattern",
            "flat_area_sq_in": "13.5",
        })
        self.assertIsNone(result["material_cost_each"])
        self.assertIsNone(result["length_in"])

    def test_assemblies_and_ambiguous_or_bad_inputs_rejected(self):
        base = {
            "scope": "individual_component", "basis": "k_factor_approximation",
            "outside_leg_sum_in": "8", "blank_width_in": "4",
            "thickness_in": ".125", "inside_radius_in": ".125",
            "bend_angle_deg": "90", "bend_count": 2,
        }
        for patch in (
            {"scope": "assembly"}, {"inside_radius_in": None},
            {"bend_count": "1.5"}, {"bend_angle_deg": "180"},
            {"outside_leg_sum_in": "-8"}, {"k_factor": "NaN"},
            {"material_price_per_sq_in": "-1"}, {"cushion_in": ".30"},
        ):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                estimate_component_blank({**base, **patch})

    def test_local_endpoint_never_approves_or_writes_quote(self):
        with app.test_client() as client:
            response = client.post("/api/blank/estimate", json={
                "scope": "individual_component", "basis": "flat_pattern",
                "flat_length_in": "4", "flat_width_in": "3",
                "material_price_per_sq_in": "1.25",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["material_cost_each"], "15.00")
            self.assertFalse(response.json["approved"])
            invalid = client.post("/api/blank/estimate", json={
                "scope": "assembly", "basis": "flat_pattern",
                "flat_length_in": "4", "flat_width_in": "3",
            })
            self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main()
