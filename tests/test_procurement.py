"""Independent offline procurement workflow tests. No live ERP receives messages."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from ezstimate.procurement import (
    create_request, get_request, recent_requests, approve_request,
    approve_and_dispatch, dispatch_request
)
from ezstimate.erp_adapters import OutboxAdapter, HttpsERPAdapter, DispatchError
from ezstimate.server import app


class FakeResponse:
    def __init__(self, status=202, body=b'{"external_reference":"PR-REMOTE-1"}'):
        self.status=status
        self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def getcode(self):return self.status
    def read(self,size=-1):return self.body[:size]


class FakeOpener:
    def __init__(self,fail=False):
        self.calls=[]
        self.fail=fail
    def open(self,req,timeout=12):
        self.calls.append(req)
        if self.fail:
            raise URLError("synthetic timeout")
        return FakeResponse()


class PurchaseRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=str(Path(self.tmp.name)/"pricing.db")
        self.outbox=str(Path(self.tmp.name)/"outbox")
        self.env=patch.dict(os.environ,{
            "EZSTIMATE_PRICE_DB":self.db,
            "EZSTIMATE_APPROVAL_TOKEN":"unit-test-approval-token",
            "EZSTIMATE_ERP_MODE":"",
            "EZSTIMATE_ERP_OUTBOX":self.outbox,
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def draft(self, **changes):
        return {"requested_by":"Test Requester","department":"Production",
                "justification":"Synthetic Job 60194-02 requires material for a scheduled build",
                "client_key":"synthetic-idempotency-1",
                "lines":[{"material_key":"sht-stl-0250x60x120-a36-hr",
                          "quantity":"5","unit":"sheet","needed_by":"2026-11-12",
                          "job":"60194-02","source_ref":"MID:forecast row 4",
                          "description":"0.250 in A36 sheet","supplier_preference":""}],
                **changes}

    def test_draft_is_durable_and_not_dispatched(self):
        created=create_request(self.draft())
        request=created["request"]
        self.assertEqual(request["status"],"draft")
        self.assertEqual(request["payload"]["lines"][0]["material_key"],
                         "SHT-STL-0250X60X120-A36-HR")
        self.assertTrue(request["payload_sha256"])
        fetched=get_request(request["request_id"])
        self.assertEqual(fetched["request"]["payload"],request["payload"])
        self.assertEqual(fetched["events"][0]["event_type"],"created")
        self.assertEqual(len(recent_requests()["requests"]),1)
        self.assertFalse(Path(self.outbox).exists())

    def test_client_dedup_prevents_modified_reuse(self):
        first=create_request(self.draft())
        same=create_request(self.draft())
        self.assertFalse(same["new"])
        self.assertEqual(first["request"]["request_id"],same["request"]["request_id"])
        with self.assertRaisesRegex(ValueError,"client_key"):
            create_request(self.draft(justification="Changed underlying request"))

    def test_approve_fails_closed_without_configured_secret(self):
        req=create_request(self.draft())["request"]
        with patch.dict(os.environ,{"EZSTIMATE_APPROVAL_TOKEN":""}):
            with self.assertRaises(PermissionError):
                approve_request(req["request_id"],"Approver","anything")
        with self.assertRaises(PermissionError):
            approve_request(req["request_id"],"Approver","wrong")
        self.assertEqual(get_request(req["request_id"])["request"]["status"],"draft")

    def test_approval_without_erp_mode_stays_approved(self):
        req=create_request(self.draft())["request"]
        result=approve_and_dispatch(req["request_id"],"Purchasing Manager",
                                    "unit-test-approval-token")
        self.assertEqual(result["request"]["status"],"approved")
        self.assertIsNone(result["delivery"])
        self.assertEqual(get_request(req["request_id"])["events"][-1]["event_type"],"approved")

    def test_approved_outbox_export_is_not_an_erp_order(self):
        with patch.dict(os.environ,{"EZSTIMATE_ERP_MODE":"outbox",
                                    "EZSTIMATE_ERP_OUTBOX_FORMAT":"json"}):
            req=create_request(self.draft())["request"]
            result=approve_and_dispatch(req["request_id"],"Purchasing Manager",
                                        "unit-test-approval-token")
            self.assertEqual(result["request"]["status"],"exported")
            self.assertEqual(result["delivery"]["transport"],"file_outbox")
            self.assertFalse(result["delivery"]["erp_accepted"])
            output=Path(result["delivery"]["path"])
            self.assertTrue(output.exists())
            data=json.loads(output.read_text("utf-8"))
            self.assertEqual(data["request_id"],req["request_id"])
            self.assertEqual(data["approval"]["approved_by"],"Purchasing Manager")
            self.assertEqual(data["payload"]["lines"][0]["quantity"],"5")
            again=dispatch_request(req["request_id"],"unit-test-approval-token")
            self.assertTrue(again["duplicate"])
            self.assertEqual(len(list(Path(self.outbox).glob("*.json"))),1)
            self.assertEqual([x["event_type"] for x in get_request(req["request_id"])["events"]],
                             ["created","approved","dispatch_started","dispatched"])

    def test_csv_escape_and_export_receipt(self):
        req=create_request(self.draft(client_key="csv-test",lines=[{
            "material_key":"A36-SHEET","quantity":"2","unit":"sheet",
            "description":"=SUM(1,2)","source_ref":"@fake",
            "job":"60194-02"}]))["request"]
        approve_request(req["request_id"],"Purchasing Manager","unit-test-approval-token")
        result=dispatch_request(req["request_id"],"unit-test-approval-token",
                                adapter=OutboxAdapter(path=self.outbox,format="csv"))
        file=Path(result["request"]["delivery_receipt"]["path"])
        csv=file.read_text("utf-8")
        self.assertIn("'=SUM(1,2)",csv)
        self.assertIn("'@fake",csv)
        self.assertFalse(result["request"]["delivery_receipt"]["erp_accepted"])

    def test_https_dispatch_requires_configured_https_url(self):
        for url in ("http://example.com/inbox","https://u:p@example.com/inbox",
                    "https://example.com/inbox?token=secret"):
            with self.assertRaises(DispatchError):
                HttpsERPAdapter(endpoint=url)
        opener=FakeOpener()
        adapter=HttpsERPAdapter(endpoint="https://erp.example.test/requisitions",
                                bearer="fake-bearer",opener=opener)
        req=create_request(self.draft())["request"]
        approve_request(req["request_id"],"Purchasing Manager","unit-test-approval-token")
        result=dispatch_request(req["request_id"],"unit-test-approval-token",adapter=adapter)
        self.assertEqual(result["request"]["status"],"endpoint_delivered")
        self.assertFalse(result["request"]["delivery_receipt"]["erp_accepted"])
        self.assertEqual(len(opener.calls),1)
        sent=opener.calls[0]
        self.assertEqual(sent.get_header("Idempotency-key"),req["request_id"])
        self.assertEqual(sent.get_header("Authorization"),"Bearer fake-bearer")
        payload=json.loads(sent.data)
        self.assertEqual(payload["payload"]["lines"][0]["unit"],"sheet")

    def test_network_timeout_never_auto_retries_uncertain_delivery(self):
        req=create_request(self.draft())["request"]
        approve_request(req["request_id"],"Purchasing Manager","unit-test-approval-token")
        opener=FakeOpener(fail=True)
        adapter=HttpsERPAdapter(endpoint="https://erp.example.test/requisitions",
                                opener=opener)
        with self.assertRaises(DispatchError) as exc:
            dispatch_request(req["request_id"],"unit-test-approval-token",adapter=adapter)
        self.assertTrue(exc.exception.uncertain)
        self.assertEqual(get_request(req["request_id"])["request"]["status"],"delivery_unknown")
        with self.assertRaisesRegex(ValueError,"reconciled"):
            dispatch_request(req["request_id"],"unit-test-approval-token",adapter=adapter)
        self.assertEqual(len(opener.calls),1)

    def test_endpoints_require_approval_then_export(self):
        with app.test_client() as client:
            r=client.post("/api/procurement/requests",json=self.draft())
            self.assertEqual(r.status_code,201)
            request_id=r.json["request"]["request_id"]
            self.assertEqual(client.post("/api/procurement/requests/"+request_id+
                                         "/approve",json={"approver":"Purchasing Manager"}).status_code,403)
            with patch.dict(os.environ,{"EZSTIMATE_ERP_MODE":"outbox"}):
                response=client.post("/api/procurement/requests/"+request_id+"/approve",
                                     headers={"X-EZstimate-Approval-Token":"unit-test-approval-token"},
                                     json={"approver":"Purchasing Manager"})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json["request"]["status"],"exported")
            self.assertTrue(client.get("/api/procurement/status").json["approval_configured"])
            self.assertEqual(client.get("/api/procurement/requests/"+request_id).json[
                "request"]["status"],"exported")


if __name__=="__main__":
    unittest.main()
