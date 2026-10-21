"""Axiom actual-invoice feedback must never silently contaminate EZstimate prices."""
from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path

from ezstimate.axiom_cost_feedback import (
    stage_axiom_cost_feedback,actual_cost_inbox,adopt_axiom_cost
)
from ezstimate.pricing import price_history


class AxiomCostFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"actual-costs.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def observation(self,**patch):
        return {
            "source":"Axiom.vendor_invoice_reconciliation",
            "price_memory_status":"review_required",
            "invoice_line_id":123,
            "material_key":"MAT-6061",
            "supplier":"Midwest Metals",
            "unit":"sheet","currency":"USD",
            "invoice_date":"2026-10-20",
            "invoice_number":"INV-456",
            "invoiced_qty":"8",
            "invoiced_unit_price":"15.25",
            "landed_unit_cost":"16.75",
            "purchase_order_unit_price":"14.00",
            "source_ref":"Invoice and packing slip",
            "document_sha256":None,
            **patch
        }

    def feed(self,records):
        return {"schema":"axiom.actual_material_cost_feedback.v1",
                "observations":records}

    def test_import_is_staging_only_then_explicit_adoption(self):
        record=self.observation()
        staged=stage_axiom_cost_feedback(self.feed([record]),path=self.db)
        self.assertEqual(staged["staged"],1)
        self.assertEqual(stage_axiom_cost_feedback(self.feed([record]),path=self.db)["staged"],0)
        self.assertEqual(actual_cost_inbox(path=self.db)[0]["status"],"pending")
        self.assertIsNone(price_history("MAT-6061","sheet",as_of="2026-10-21",
                                        path=self.db)["candidate"])
        accepted=adopt_axiom_cost("AXIOM-INVOICE-LINE-123","local purchasing reviewer",path=self.db)
        self.assertTrue(accepted["new"])
        actual=price_history("MAT-6061","sheet",as_of="2026-10-21",
                             path=self.db)["candidate"]
        self.assertEqual(actual["source_type"],"invoice")
        self.assertEqual(actual["unit_price"],"15.25")
        self.assertEqual(actual["quantity"],"8")
        self.assertIn("16.75",actual["notes"])
        self.assertFalse(adopt_axiom_cost("AXIOM-INVOICE-LINE-123","reviewer",path=self.db)["new"])

    def test_conflicting_replay_is_rejected_without_changing_memory(self):
        original=self.observation()
        stage_axiom_cost_feedback(self.feed([original]),path=self.db)
        changed=self.observation(invoiced_unit_price="16.25")
        with self.assertRaisesRegex(ValueError,"different evidence"):
            stage_axiom_cost_feedback(self.feed([changed]),path=self.db)
        self.assertEqual(len(actual_cost_inbox(path=self.db)),1)
        self.assertEqual(actual_cost_inbox(path=self.db)[0]["status"],"pending")

    def test_atomic_multi_item_staging_and_currency_unit_validation(self):
        valid=self.observation()
        invalid=self.observation(invoice_line_id=124,unit="ton")
        with self.assertRaisesRegex(ValueError,"unsupported"):
            stage_axiom_cost_feedback(self.feed([valid,invalid]),path=self.db)
        self.assertEqual(actual_cost_inbox(path=self.db),[])
        for value,field in [("EUR","currency"),("NaN","invoiced_unit_price"),
                            ("0","invoiced_qty")]:
            record=self.observation(**{field:value})
            with self.assertRaises(ValueError):
                stage_axiom_cost_feedback(self.feed([record]),path=self.db)
        with self.assertRaisesRegex(ValueError,"Duplicate invoice"):
            stage_axiom_cost_feedback(self.feed([valid,valid]),path=self.db)

    def test_landed_price_must_not_replace_actual_material_price(self):
        source=self.observation(invoiced_unit_price="12.40",
                                landed_unit_cost="19.90",
                                purchase_order_unit_price="10.00")
        stage_axiom_cost_feedback(self.feed([source]),path=self.db)
        with self.assertRaisesRegex(ValueError,"Reviewer"):
            adopt_axiom_cost("AXIOM-INVOICE-LINE-123","",path=self.db)
        adopt_axiom_cost("AXIOM-INVOICE-LINE-123","reviewer",path=self.db)
        actual=price_history("MAT-6061","sheet",as_of="2026-10-21",
                             path=self.db)["candidate"]
        self.assertEqual(actual["unit_price"],"12.40")
        self.assertNotEqual(actual["unit_price"],"19.90")
