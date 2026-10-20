import io
import unittest
import fitz

from ezstimate.engine import inspect_document, review_package
from ezstimate.server import app


class IntegrationTests(unittest.TestCase):
    def test_po_pdf_fields(self):
        pdf = fitz.open()
        page = pdf.new_page(width=600, height=800)
        page.insert_text((310, 590), "PURCHASE ORDER # PO-2026")
        page.insert_text((310, 610), "PART NO: BR-200")
        page.insert_text((310, 630), "QTY: 15")
        page.insert_text((310, 650), "REQUIRED BY: 11/14/2026")
        page.insert_text((310, 670), "UNIT PRICE: 12.50")
        page.insert_text((310, 690), "NET 30")
        result = inspect_document("customer-po.pdf", pdf.tobytes())
        pdf.close()
        self.assertEqual(result["kind"], "purchase_order")
        self.assertEqual(result["fields"]["part_number"]["value"], "BR-200")
        self.assertEqual(result["fields"]["required_date"]["value"], "11/14/2026")
        self.assertEqual(result["fields"]["po_unit_price"]["value"], "12.50")
        self.assertEqual(result["fields"]["payment_terms"]["value"], "NET 30")
        self.assertTrue(result["fields"]["required_date"]["needs_review"])

    def test_po_bom_qty_disagreement(self):
        po = {"filename": "po.pdf", "kind": "purchase_order", "fields": {
            "part_number": {"value": "P-100", "source": "po.pdf"},
            "quantity": {"value": "30", "source": "po.pdf"}},
            "warnings": []}
        bom = {"filename": "bom.csv", "kind": "bom", "fields": {},
               "bom": [{"part_number": "P-100", "quantity": 25}],
               "warnings": []}
        findings = review_package([po, bom])
        self.assertTrue(any("PO quantity differs" in item["message"] for item in findings))

    def test_flask_local_workbench(self):
        with app.test_client() as client:
            for endpoint in ("/", "/app.js", "/style.css", "/bean-official.webp", "/api/status"):
                self.assertEqual(client.get(endpoint).status_code, 200, endpoint)
            result = client.post("/api/intake", data={"files": (io.BytesIO(
                b"Part Number,Qty,Material\nX-20,2,A36\n"), "bom.csv")})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["documents"][0]["bom"][0]["quantity"], 2)
            response = client.post("/api/quote", json={"lines": [{
                "part_number": "X-20", "quantity": 2, "material_cost_each": 20,
                "labor_hours_each": 0, "outside_cost_each": 0, "setup_cost_total": 0,
                "scrap_pct": 0, "margin_pct": 20}]})
            self.assertEqual(response.json["total"], "50.00")
            self.assertEqual(response.json["approval"], "not approved")


if __name__ == "__main__":
    unittest.main()
