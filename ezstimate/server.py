"""Local-only EZstimate Gothic Lime workbench and real estimation API."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from .core import analyze_pdf, import_bom, quote_proposal
from .bean import send_to_bean_inbox

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EZstimate | Estimating Workbench</title><style>
:root{color-scheme:dark;--bg:#0F1113;--panel:#1A1D20;--raised:#22282A;--line:#303A3B;--text:#E6EAE7;--muted:#9FAEB0;--accent:#79DE4B}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,Segoe UI}
header{display:flex;justify-content:space-between;padding:18px 24px;background:var(--panel);border-bottom:1px solid var(--line)}
.brand{font-size:24px;font-weight:900;color:var(--accent)}main{max-width:1200px;margin:auto;padding:20px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:14px}
h1{margin:0;font-size:27px}h2{font-size:17px}p,label,small{color:var(--muted)}
label{display:block;margin-bottom:8px;font-weight:700}
input{width:100%;display:block;padding:9px;margin-top:4px;background:var(--raised);color:var(--text);border:1px solid var(--line);border-radius:8px}
button{padding:10px 13px;background:var(--accent);color:#0F160D;border:0;border-radius:8px;font-weight:800;cursor:pointer}
button.secondary{background:var(--raised);color:var(--text);border:1px solid var(--line)}
button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--raised);padding:12px;border-radius:8px;max-height:300px;overflow:auto}
.costs{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px}
@media(max-width:740px){.grid,.costs{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;scroll-behavior:auto!important}}
</style></head><body><header><div><div class="brand">EZstimate</div><small>Engineering Suite · BEAN Gothic Lime</small></div><small id="beanStatus">BEAN · local checks only</small></header>
<main><h1>Estimate from evidence.</h1><p>Documents propose facts. Only entered costs determine prices. REVIEW REQUIRED until a person approves.</p>
<div class="grid"><div><section><h2>1 · Import documents</h2>
<label>Drawing or PO PDF<input id="pdf" type="file" accept=".pdf"></label>
<label>CSV/XLSX BOM<input id="bom" type="file" accept=".csv,.xlsx"></label>
<pre id="evidence">No evidence yet.</pre></section>
<section><h2>2 · Review candidates</h2><p>Verify drawing revision, material, PO terms, BOM quantities and tolerances. No OCR or cost lookup is implied.</p><strong>REVIEW REQUIRED</strong></section></div>
<div><section><h2>3 · Actual costing</h2><label>Quote number<input id="quote" value="DRAFT-001"></label><div id="costInputs" class="costs"></div>
<p>All costs USD. Fractional rates: 0.10 means 10%.</p><button id="compute">Calculate proposed quote</button></section>
<section><h2>4 · Draft results</h2><p id="status">No quote yet.</p><pre id="result">Real calculations appear here.</pre>
<button id="download" class="secondary" disabled>Export proposal JSON</button>
<button id="bean" class="secondary" disabled>Send unverified BEAN note</button></section></div></div></main>
<script>
const fields=["quantity","material_unit_cost","labor_hours_per_unit","labor_rate_per_hour","setup_hours","setup_rate_per_hour","outside_unit_cost","scrap_rate","overhead_rate","margin_rate"];
let drawing=null,bom=null,proposal=null;const el=id=>document.getElementById(id);
fields.forEach((key,i)=>{let label=document.createElement("label");label.textContent=key.replaceAll("_"," ");let inp=document.createElement("input");inp.id=key;inp.type="number";inp.step="any";inp.min="0";inp.value=i===0?"1":"0";label.append(inp);el("costInputs").append(label)});
async function api(path,body,binary=false){let r=await fetch(path,{method:"POST",headers:{"Content-Type":binary?"application/octet-stream":"application/json"},body:binary?body:JSON.stringify(body)});let data=await r.json();if(!r.ok)throw Error(data.error||"Request failed");return data}
async function upload(file,kind){if(!file)return;try{let d=await api("/api/"+kind+"?filename="+encodeURIComponent(file.name),await file.arrayBuffer(),true);if(kind==="pdf")drawing=d;else bom=d;el("evidence").textContent=JSON.stringify({drawing,bom},null,2)}catch(e){el("status").textContent=e.message}}
el("pdf").onchange=e=>upload(e.target.files[0],"pdf");el("bom").onchange=e=>upload(e.target.files[0],"bom");
el("compute").onclick=async()=>{try{let inputs={};fields.forEach(k=>inputs[k]=el(k).value);proposal=await api("/api/quote",{quote_number:el("quote").value,inputs,drawing,bom});el("result").textContent=JSON.stringify(proposal,null,2);el("status").textContent="REVIEW REQUIRED | USD "+proposal.pricing.quoted_total;el("download").disabled=false;el("bean").disabled=false}catch(e){el("status").textContent=e.message}};
el("download").onclick=()=>{if(!proposal)return;let u=URL.createObjectURL(new Blob([JSON.stringify(proposal,null,2)],{type:"application/json"}));let a=document.createElement("a");a.href=u;a.download="EZstimate-quote.json";a.click();URL.revokeObjectURL(u)};
el("bean").onclick=async()=>{try{let r=await api("/api/bean",{proposal});el("status").textContent="BEAN note receipt: "+r.receipt}catch(e){el("status").textContent=e.message}};
fetch("/api/status").then(x=>x.json()).then(x=>el("beanStatus").textContent=x.bean_connected?"BEAN inbox configured":"BEAN · local checks only");
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data):
        content=json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(content)))
        self.end_headers();self.wfile.write(content)

    def do_GET(self):
        if self.path=="/":
            data=HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers();self.wfile.write(data)
        elif self.path=="/api/status":
            inbox=os.getenv("EZSTIMATE_BEAN_INBOX","")
            self.respond(200,{"bean_connected":bool(inbox and Path(inbox).is_dir())})
        else:self.respond(404,{"error":"not found"})

    def do_POST(self):
        if self.headers.get("Origin") and self.headers["Origin"] not in ("http://127.0.0.1:8765","http://localhost:8765"):
            self.respond(403,{"error":"cross-origin denied"});return
        try:
            length=int(self.headers.get("Content-Length","-1"))
            if length<0 or length>20_000_000:raise ValueError("missing or excessive upload size")
            raw=self.rfile.read(length)
            u=urlparse(self.path)
            if u.path in ("/api/pdf","/api/bom"):
                name=parse_qs(u.query).get("filename",["upload.pdf"])[0]
                value=analyze_pdf(raw,filename=name) if u.path=="/api/pdf" else import_bom(raw,filename=name)
            else:
                data=json.loads(raw.decode("utf-8"))
                if u.path=="/api/quote":
                    value=quote_proposal(data["quote_number"],data["inputs"],drawing=data.get("drawing"),bom=data.get("bom"))
                elif u.path=="/api/bean":
                    folder=os.getenv("EZSTIMATE_BEAN_INBOX","")
                    if not folder:raise ValueError("BEAN Core inbox not configured")
                    value={"receipt":str(send_to_bean_inbox(data["proposal"],folder))}
                else:self.respond(404,{"error":"not found"});return
            self.respond(200,value)
        except (ValueError,KeyError,TypeError) as exc:self.respond(400,{"error":str(exc)})

def main():
    print("EZstimate: http://127.0.0.1:8765 (loopback only)")
    ThreadingHTTPServer(("127.0.0.1",8765),Handler).serve_forever()
if __name__=="__main__":main()
