"""Synthetic tests for source-backed fabrication candidates."""
import unittest
import fitz
from ezstimate.fabrication import extract_fabrication_features
from ezstimate.engine import inspect_document


class FabricationCandidatesTests(unittest.TestCase):
    def test_reviewable_explicit_bend_and_weld_notes(self):
        regions = [{"text": "3X BEND R.125 90 DEG\n3/16 FILLET WELD LENGTH 10 IN\nR.500 EDGE\n",
                    "page": 2, "region": "full page"}]
        features = extract_fabrication_features(regions, "synthetic-bracket.pdf")
        self.assertEqual([f["process"] for f in features], ["bending", "welding"])
        bend, weld = features
        self.assertEqual(bend["attributes"]["radius"], ".125")
        self.assertEqual(bend["attributes"]["count"], 3)
        self.assertEqual(bend["attributes"]["angle_degrees"], "90")
        self.assertEqual(weld["attributes"]["size"], "3/16")
        self.assertEqual(weld["attributes"]["length"], "10")
        self.assertEqual(weld["attributes"]["length_unit"], "IN")
        self.assertEqual(weld["page"], 2)
        self.assertTrue(all(f["needs_review"] and f["status"] == "proposed" for f in features))

    def test_missing_details_remain_unknown_and_no_duplicate_title_crop(self):
        regions = [{"text": "BEND AS SHOWN\nWELD PER PRINT", "page": 1, "region": "full page"},
                   {"text": "BEND AS SHOWN", "page": 1, "region": "lower-right title block"}]
        bend, weld = extract_fabrication_features(regions, "synthetic.pdf")
        self.assertIsNone(bend["attributes"]["radius"])
        self.assertIsNone(bend["attributes"]["count"])
        self.assertIsNone(weld["attributes"]["length"])

    def test_pdf_intake_exposes_candidates_not_prices_or_geometry_claims(self):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "2 BENDS R.250 90 DEG")
        page.insert_text((72, 120), "1/4 FILLET WELD LENGTH 8 IN")
        payload = doc.tobytes()
        doc.close()
        result = inspect_document("fabrication.pdf", payload)
        found = result["fabrication_features"]
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0]["attributes"]["count"], 2)
        self.assertEqual(found[1]["attributes"]["size"], "1/4")
        self.assertFalse(any("estimated_hours" in f or "cost" in f for f in found))


if __name__ == "__main__":
    unittest.main()
