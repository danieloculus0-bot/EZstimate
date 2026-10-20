"""ERP-neutral purchase-request adapters.

Adapter contract: deliver(canonical_requisition) -> transport receipt.
An HTTP 2xx proves delivery to an endpoint, NOT ERP requisition acceptance.
Providers such as JobBOSS, Dynamics, SAP, NetSuite, or Epicor require their own
documented field mapping and API-specific acknowledgement adapter.
"""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class DispatchError(RuntimeError):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain=uncertain


class OutboxAdapter:
    mode="outbox"
    def __init__(self,path=None,format=None):
        self.path=Path(path or os.environ.get("EZSTIMATE_ERP_OUTBOX","") or
                       (Path.home()/".ezstimate"/"erp_outbox"))
        self.format=format or os.environ.get("EZSTIMATE_ERP_OUTBOX_FORMAT","json")
        if self.format not in ("json","csv"):
            raise DispatchError("ERP outbox format must be json or csv")

    def deliver(self,request):
        request_id=request["request_id"]
        if not request_id.startswith("PR-") or not request_id[3:].isalnum():
            raise DispatchError("Invalid purchase request ID")
        try:
            self.path.mkdir(parents=True,exist_ok=True)
        except OSError as exc:
            raise DispatchError("Could not create ERP export directory") from exc
        if self.format=="json":
            body=(json.dumps({"schema":"axiom.purchase_request.dispatch.v1",**request},
                             sort_keys=True,indent=2)+"\n").encode("utf-8")
        else:
            stream=io.StringIO(newline="")
            writer=csv.writer(stream)
            writer.writerow(["request_id","approval_sha256","approved_by","approved_utc",
                "requested_by","department","material_key","description","quantity",
                "unit","needed_by","job","supplier_preference","source_ref","justification"])
            for item in request["payload"]["lines"]:
                # Avoid spreadsheet formula execution when importing untrusted descriptions.
                def safe(value):
                    text=str(value or "")
                    return "'"+text if text.lstrip().startswith(("=","+","-","@")) else text
                writer.writerow([safe(request_id),safe(request["approval"]["approval_sha256"]),
                    safe(request["approval"]["approved_by"]),safe(request["approval"]["approved_utc"]),
                    safe(request["payload"]["requested_by"]),safe(request["payload"]["department"]),
                    safe(item["material_key"]),safe(item["description"]),safe(item["quantity"]),
                    safe(item["unit"]),safe(item["needed_by"]),safe(item["job"]),
                    safe(item["supplier_preference"]),safe(item["source_ref"]),
                    safe(request["payload"]["justification"])])
            body=stream.getvalue().encode("utf-8")
        target=self.path/(request_id+"."+self.format)
        try:
            # An existing export is not overwritten; identical content is idempotent.
            with target.open("xb") as out:
                out.write(body)
            try:
                os.chmod(target,0o600)
            except OSError:
                pass
            duplicate=False
        except FileExistsError:
            if target.read_bytes()!=body:
                raise DispatchError("ERP outbox file already exists with different content")
            duplicate=True
        except OSError as exc:
            raise DispatchError("Unable to write ERP outbox file") from exc
        return {"transport":"file_outbox","format":self.format,"path":str(target),
                "existing_identical":duplicate,"erp_accepted":False,
                "message":"Export ready for ERP import; no ERP acknowledgement"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


class HttpsERPAdapter:
    mode="https"
    def __init__(self,endpoint=None,bearer=None,timeout=12,opener=None):
        self.endpoint=endpoint or os.environ.get("EZSTIMATE_ERP_ENDPOINT","")
        target=urlsplit(self.endpoint)
        if (target.scheme!="https" or not target.hostname or target.username or
            target.password or target.fragment or target.query):
            raise DispatchError("ERP endpoint must be a configured HTTPS URL without credentials or query")
        self.bearer=bearer if bearer is not None else os.environ.get("EZSTIMATE_ERP_BEARER_TOKEN","")
        self.timeout=timeout
        self.opener=opener or build_opener(NoRedirect())

    def deliver(self,request):
        body=json.dumps({"schema":"axiom.purchase_request.dispatch.v1",**request},
                        separators=(",",":"),sort_keys=True).encode("utf-8")
        headers={"Content-Type":"application/json","Accept":"application/json",
                 "Idempotency-Key":request["request_id"],
                 "X-EZstimate-Approval-Digest":request["approval"]["approval_sha256"]}
        if self.bearer:
            headers["Authorization"]="Bearer "+self.bearer
        req=Request(self.endpoint,data=body,headers=headers,method="POST")
        try:
            with self.opener.open(req,timeout=self.timeout) as response:
                status=response.getcode()
                receipt=response.read(4096)
        except HTTPError as exc:
            raise DispatchError("ERP endpoint HTTP "+str(exc.code),
                                uncertain=exc.code>=500) from exc
        except (URLError,TimeoutError,OSError) as exc:
            raise DispatchError("ERP connection uncertain; reconcile by request ID before retry",
                                uncertain=True) from exc
        if status not in (200,201,202):
            raise DispatchError("ERP endpoint did not confirm delivery",uncertain=True)
        try:
            parsed=json.loads(receipt) if receipt else None
        except (UnicodeError,ValueError):
            parsed=None
        # Never infer an accepted ERP PR from arbitrary webhook response.
        return {"transport":"https","http_status":status,"endpoint":self.endpoint,
                "provider_response":parsed if isinstance(parsed,dict) else None,
                "erp_accepted":False,
                "message":"HTTPS endpoint responded; ERP creation not independently confirmed"}


def adapter_from_environment():
    mode=os.environ.get("EZSTIMATE_ERP_MODE","").lower()
    if mode=="outbox":
        return OutboxAdapter()
    if mode=="https":
        return HttpsERPAdapter()
    raise DispatchError("Configure EZSTIMATE_ERP_MODE as outbox or https before dispatch")
