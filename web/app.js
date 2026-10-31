"use strict";
// EZstimate browser client, backed by local Python quote engine.
const st={documents:[],issues:[],rows:[],quote:null,bean:null,priceCandidate:null};
const byId=id=>document.getElementById(id);
const cols=["part_number","quantity","material_cost_each","labor_hours_each","shop_rate_per_hour",
            "outside_cost_each","setup_cost_total","scrap_pct","margin_pct"];
const labels=["Part","Quantity","Material cost","Labor hours","Shop rate","Outside cost","Setup cost","Scrap percent","Gross margin percent"];
function el(tag,text,cls){const x=document.createElement(tag);if(text!==null&&text!==undefined)x.textContent=String(text);if(cls)x.className=cls;return x;}
function clear(x){x.replaceChildren();}
function status(message,bad=false){byId("message").textContent=message;byId("message").className="notice"+(bad?" error":"");}
async function req(path,opts){const r=await fetch(path,opts);const j=await r.json();if(!r.ok)throw Error(j.error||"Request failed");return j;}
function source(v){return (v.source||"manual")+(v.page?" · p"+v.page:"")+(v.region?" · "+v.region:"")+(v.row?" · row "+v.row:"");}
function addRow(v={}){
 st.rows.push({part_number:v.part_number||"",quantity:v.quantity||1,source:v.source||"manual",
 material_cost_each:"",labor_hours_each:"",shop_rate_per_hour:"",
 outside_cost_each:"0",setup_cost_total:"0",scrap_pct:"0",margin_pct:"0"});
 renderRows();
}
function renderRows(){
 const t=byId("lines");clear(t);
 st.rows.forEach((row,index)=>{
   const tr=el("tr");
   cols.forEach((field,i)=>{
     const td=el("td"),inp=el("input");
     inp.className=field==="part_number"?"part":"";
     if(field!=="part_number"){inp.type="number";inp.step=field==="quantity"?"1":"any";inp.min="0";}
     inp.value=row[field];inp.setAttribute("aria-label",labels[i]+" line "+(index+1));
     inp.addEventListener("input",()=>{row[field]=inp.value;st.quote=null;byId("export").disabled=true;
       byId("total").textContent="N/A";byId("quote-status").textContent="Inputs changed. Recalculate.";});
     td.append(inp);
     if(field==="part_number")td.append(el("small",row.source||"manual"));
     tr.append(td);
   });
   const td=el("td"),remove=el("button","×","remove");remove.setAttribute("aria-label","Remove row "+(index+1));
   remove.addEventListener("click",()=>{st.rows.splice(index,1);st.quote=null;byId("export").disabled=true;renderRows();});
   td.append(remove);tr.append(td);t.append(tr);
 });
 const target=byId("price-line");
 if(target){
   const prior=target.value;clear(target);
   const defaultOption=el("option","Select a quote line");defaultOption.value="";target.append(defaultOption);
   st.rows.forEach((row,index)=>{const o=el("option",(index+1)+": "+(row.part_number||"Unnamed"));o.value=String(index);target.append(o);});
   target.value=prior && Number(prior)<st.rows.length?prior:"";
   byId("apply-price").disabled=!(st.priceCandidate&&st.priceCandidate.price_unit==="ea"&&target.value!=="");
 }
}
function renderDocs(){
 clear(byId("documents"));clear(byId("exceptions"));
 if(!st.documents.length)byId("documents").append(el("p","No documents loaded."));
 for(const d of st.documents){
   const card=el("div",null,"record");card.append(el("strong",d.filename+" · "+d.kind.replaceAll("_"," ")));
   let count=0;
   for(const [key,v] of Object.entries(d.fields||{})){
     const p=el("div",null,"detail");p.append(el("span",key.replaceAll("_"," ")+": "+v.value));
     p.append(el("small",source(v)+" · proposed"));card.append(p);count++;
   }
   if(!count)card.append(el("div","No named fields extracted.","detail"));
   card.append(el("small",(d.bom||[]).length+" BOM row(s) detected"));
   for(const f of (d.fabrication_features||[])){
     const details=Object.entries(f.attributes||{}).filter(([,v])=>v!==null&&v!=="")
       .map(([key,val])=>key.replaceAll("_"," ")+": "+val).join(", ");
     card.append(el("div",f.process+" · "+(details||"details unknown")+" · "+source(f)+" · review drawing callout","detail"));
   }
   if(d.process_hints&&d.process_hints.length)card.append(el("small",
       "Process clues: "+d.process_hints.map(v=>v.value).join(", ")+" (unverified)"));
   byId("documents").append(card);
 }
 if(!st.issues.length)byId("exceptions").append(el("p","No automated exceptions. Verify manually."));
 for(const issue of st.issues){
   const card=el("div",issue.message,"record warning");
   card.append(el("small",(issue.sources||[]).join(", ")));byId("exceptions").append(card);
 }
}
function body(){return {lines:st.rows.map(row=>({...row}))};}
async function scan(){
 const chosen=byId("files").files;
 if(!chosen.length){status("Select at least one drawing, PO or BOM.",true);return;}
 byId("scan").disabled=true;status("Inspecting documents locally...");
 try{
   const fd=new FormData();for(const file of chosen)fd.append("files",file,file.name);
   const j=await req("/api/intake",{method:"POST",body:fd});
   st.documents=j.documents;st.issues=j.issues;st.rows=[];st.quote=null;st.bean=null;
   for(const d of st.documents){
     if(d.bom&&d.bom.length){for(const row of d.bom)addRow(row);}
     else if(d.kind==="drawing"&&d.fields.part_number)addRow({
       part_number:d.fields.part_number.value,
       quantity:d.fields.quantity?Number(d.fields.quantity.value):1,source:d.filename});
   }
   renderDocs();renderRows();byId("total").textContent="N/A";byId("export").disabled=true;
   byId("quote-status").textContent="Cost inputs required.";
   const errors=(j.errors||[]).map(x=>x.filename+": "+x.message);
   status(st.documents.length+" document(s) inspected; "+st.rows.length+" candidate quote line(s)."
       +(errors.length?" Errors: "+errors.join("; "):""),errors.length>0);
 }catch(err){status(err.message,true);}
 finally{byId("scan").disabled=false;}
}
async function calculate(){
 try{
   const j=await req("/api/quote",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body())});
   st.quote=j;byId("total").textContent=j.total===null?"N/A":"$"+Number(j.total).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
   byId("quote-status").textContent=j.status==="draft_review"?"Draft calculated · NOT APPROVED":
      "Incomplete: "+(j.issues||[]).join("; ");
   clear(byId("quote-details"));
   for(const line of j.lines){
     byId("quote-details").append(el("div",
       line.part_number+" · "+(line.extended_sell===null?"incomplete":"$"+line.extended_sell+" total / $"+line.unit_sell+" each"),
       "record"));
   }
   byId("export").disabled=false;
 }catch(err){status(err.message,true);}
}
async function beanReview(journal){
 try{
   const j=await req("/api/bean/review",{method:"POST",headers:{"Content-Type":"application/json"},
     body:JSON.stringify({documents:st.documents,quote:body(),journal})});
   st.bean=j;const box=byId("bean-findings");clear(box);box.append(el("strong",j.review.engine));
   const list=el("ul");for(const finding of j.review.findings)list.append(el("li",finding));
   box.append(list);
   if(journal){
     box.append(el("p",j.journal&&j.journal.connected?
         "BEAN Core observation persisted, event #"+j.journal.event_id+". Quote remains unapproved.":
         "BEAN journal not connected: "+(j.journal?j.journal.reason:"no persistence confirmed")));
   }
 }catch(err){byId("bean-findings").textContent=err.message;}
}
async function core(){
 try{const s=await req("/api/status");
   const wired=s.bean.configured&&s.bean.core_importable;
   byId("journal-bean").disabled=!wired;
   byId("connection").textContent=wired?"BEAN CORE CONFIGURED":"BEAN · LOCAL CHECKS";
   byId("bean-mode").textContent=wired?"Core journal available · local review":"Local checks only";
 }catch(err){byId("connection").textContent="Server status unavailable";}
}
function save(){
 if(!st.quote)return;
 const payload={schema:"ezstimate.quote-draft.v1",generated_at:new Date().toISOString(),
   release_state:"not approved",documents:st.documents,inputs:body(),quote:st.quote,bean_review:st.bean};
 const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}));
 const a=el("a");a.href=url;a.download="ezstimate-draft.json";document.body.append(a);a.click();a.remove();URL.revokeObjectURL(url);
}
byId("scan").addEventListener("click",scan);
byId("addline").addEventListener("click",()=>addRow());
byId("calculate").addEventListener("click",calculate);
byId("review-bean").addEventListener("click",()=>beanReview(false));
byId("journal-bean").addEventListener("click",()=>beanReview(true));
byId("export").addEventListener("click",save);

function priceRequestBody(){
  return {material_key:byId("price-key").value.trim(),supplier:byId("price-supplier").value.trim(),
    source_type:byId("price-source-type").value,source_ref:byId("price-source-ref").value.trim(),
    effective_date:byId("price-date").value,unit_price:byId("price-value").value,
    quantity:byId("price-qty").value,price_unit:byId("price-unit").value,currency:"USD"};
}
function pricingMessage(msg,bad=false){
  const node=byId("price-history");node.textContent=msg;
  node.className="findings"+(bad?" notice error":"");
}
async function loadHistoricalPrices(){
  st.priceCandidate=null;byId("apply-price").disabled=true;
  try{
    const key=byId("price-key").value.trim(),unit=byId("price-unit").value;
    const j=await req("/api/pricing/prices?material_key="+encodeURIComponent(key)+
      "&price_unit="+encodeURIComponent(unit));
    const node=byId("price-history");clear(node);
    node.append(el("strong",j.history.length+" source-matched price record(s)"));
    if(!j.candidate){node.append(el("p","No previous price for this exact material key and unit."));return;}
    const p=j.candidate;st.priceCandidate=p;
    node.append(el("p","Most recent: $"+p.unit_price+"/"+p.price_unit+" from "+p.supplier+
      " · "+p.source_type+" "+p.source_ref+" · "+p.effective_date+
      " ("+p.age_days+" days old)"+(p.stale_90d?" · STALE >90 DAYS":"")));
    for(const row of j.history.slice(0,8))
      node.append(el("div",row.effective_date+" · $"+row.unit_price+"/"+row.price_unit+
        " · "+row.supplier+" · "+row.source_type+" "+row.source_ref,"record"));
    node.append(el("p","Reference only. No price has been applied to the quote."));
    byId("apply-price").disabled=!(p.price_unit==="ea"&&byId("price-line").value!=="");
  }catch(e){pricingMessage(e.message,true);}
}
async function saveObservedPrice(){
  try{
    const j=await req("/api/pricing/prices",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(priceRequestBody())});
    pricingMessage(j.new?"Verified supplier price retained in local SQLite.":"This source is already recorded.");
    await loadHistoricalPrices();
  }catch(e){pricingMessage(e.message,true);}
}
function applyHistoryToLine(){
  const rowId=byId("price-line").value,p=st.priceCandidate;
  if(!p||p.price_unit!=="ea"||rowId===""||!st.rows[Number(rowId)]){
    pricingMessage("Choose a price-per-each candidate and an estimate line first.",true);return;
  }
  // Deliberate user action; there is no unit conversion or silent autofill.
  st.rows[Number(rowId)].material_cost_each=p.unit_price;
  st.rows[Number(rowId)].source=(st.rows[Number(rowId)].source||"manual")+
    " | price evidence: "+p.source_type+" "+p.source_ref;
  st.quote=null;byId("export").disabled=true;byId("total").textContent="N/A";
  byId("quote-status").textContent="Historic unit cost applied manually. Recalculate and verify.";
  renderRows();pricingMessage("Applied $"+p.unit_price+"/ea from "+p.source_ref+
    " to line "+(Number(rowId)+1)+". Check material identity and quantities before releasing a quote.");
}
function marketRecord(){
  return {series:byId("market-series").value,value:byId("market-value").value,
    effective_date:byId("market-date").value,source:byId("market-source").value.trim()};
}
async function saveSignal(){
  try{
    const j=await req("/api/pricing/signals",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(marketRecord())});
    byId("market-results").textContent=j.new?"Dated market reading stored locally.":"That reading already exists.";
    await assessPressure();
  }catch(e){byId("market-results").textContent="Reading not saved: "+e.message;}
}
async function assessPressure(){
  const node=byId("market-results");
  try{
    const j=await req("/api/pricing/pressure?family="+encodeURIComponent(byId("market-family").value));
    clear(node);node.append(el("strong","Market pressure: "+j.risk.toUpperCase()+
      " · score "+j.pressure_score+" · "+j.comparison_series+" comparable series"));
    for(const item of j.factors){
      const info=item.status==="missing"?"No data":
        (item.latest.value+" "+item.latest.unit+" as of "+item.latest.effective_date+
        " from "+item.latest.source+(item.change_pct===null?" · no comparison yet":
        " · change "+item.change_pct+"%")+
        (item.status==="stale"?" · STALE":""));
      node.append(el("div",item.series+": "+info,"record"));
    }
    node.append(el("p",j.disclaimer));
  }catch(e){node.textContent="Market pressure unavailable: "+e.message;}
}
async function journalPressure(){
  const node=byId("market-results");
  try{
    const j=await req("/api/bean/market-observation",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({family:byId("market-family").value})});
    node.append(el("p",j.journal.connected?"BEAN Core journal event "+j.journal.event_id+
      " recorded. Market finding remains advisory.":"BEAN Core is not connected: "+j.journal.reason));
  }catch(e){node.append(el("p","Cannot journal to BEAN: "+e.message));}
}
async function previewMidWorkbook(){
  const file=byId("mid-file").files[0],node=byId("mid-results");
  if(!file){node.textContent="Choose an MID XLSX file first.";return;}
  byId("mid-preview").disabled=true;node.textContent="Inspecting workbook locally...";
  try{
    const form=new FormData();form.append("file",file,file.name);
    const j=await req("/api/pricing/mid-preview",{method:"POST",body:form});
    clear(node);
    node.append(el("strong",j.demand_event_count+" material events · "+
      j.buyer_action_count+" buyer queue rows · "+j.buy_now_count+" buy-now actions"));
    node.append(el("p","Sheets: "+j.recognized_formats.join(", ")+
      (j.preview_truncated?" · only first 150 of each record type shown":"")));
    for(const row of j.actions.slice(0,10)){
      const card=el("div",null,"record");
      card.append(el("div",row.action+" · "+row.material_key+
        (row.buy_qty?" · buy "+row.buy_qty:"")+
        (row.order_by?" · order by "+row.order_by:"")+
        " · "+row.source_sheet+" row "+row.source_row));
      const use=el("button","Prepare purchase request","secondary");
      use.addEventListener("click",()=>{
        byId("pr-material").value=row.material_key;
        byId("pr-quantity").value=Number(row.buy_qty)>0?row.buy_qty:"";
        byId("pr-job").value=row.job||"";
        byId("pr-supplier").value=row.supplier||"";
        byId("pr-need-date").value=/^\\d{4}-\\d{2}-\\d{2}$/.test(row.job_due)?row.job_due:"";
        byId("pr-source-ref").value=j.source_file+" / "+row.source_sheet+" / row "+row.source_row;
        byId("pr-justification").value=row.action+"; "+(row.notes||"Material forecast action");
        byId("pr-draft-result").textContent="MID evidence copied. Confirm purchasing unit and quantity before creating a draft. Nothing was sent.";
        document.getElementById("procurement").scrollIntoView({behavior:"smooth"});
      });
      card.append(use);node.append(card);
    }
    if(!j.actions.length)
      for(const row of j.events.filter(x=>x.risk_flag).slice(0,10))
        node.append(el("div",row.material_key+" · "+row.event_type+" · "+
          row.risk_flag+" · "+row.source_sheet+" row "+row.source_row,"record"));
    node.append(el("p","Read-only preview. No forecast quantities or unit prices have been added to your estimate."));
  }catch(e){node.textContent="MID import failed: "+e.message;}
  finally{byId("mid-preview").disabled=false;}
}

async function refreshOfficialFeeds(){
  const node=byId("feed-results"),button=byId("sync-official");
  button.disabled=true;node.textContent="Fetching official published indexes on the local server...";
  try{
    const j=await req("/api/pricing/feeds/refresh",{method:"POST"});
    clear(node);
    node.append(el("strong","Official feed refresh: "+j.status+
      " · "+j.saved+" new readings, "+j.unchanged+" unchanged, "+j.conflicts+" revisions to review"));
    for(const [name,p] of Object.entries(j.providers)){
      node.append(el("div",name+": "+p.status+
        (p.observations?" ("+p.observations+" observations)":"")+
        (p.hint?" · "+p.hint:"")+
        (p.error?" · "+p.error:""),"record"));
    }
    for(const issue of j.errors.slice(0,5))node.append(el("p",issue));
    await assessPressure();
  }catch(e){node.textContent="Provider refresh failed: "+e.message;}
  finally{button.disabled=false;}
}
function forecastInput(){
  return {material_key:byId("price-key").value.trim(),
    supplier:byId("price-supplier").value.trim(),
    price_unit:byId("price-unit").value,quantity:byId("price-qty").value,
    material_family:byId("market-family").value,
    horizon_days:Number(byId("forecast-horizon").value),
    spike_threshold_pct:byId("forecast-threshold").value};
}
async function freezePriceForecast(){
  const node=byId("forecast-results"),button=byId("freeze-forecast");
  button.disabled=true;
  try{
    const j=await req("/api/pricing/forecasts",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(forecastInput())});
    node.textContent=(j.new?"New":"Existing")+" source-frozen warning: "+
      j.record.material_key+" · "+j.record.risk.toUpperCase()+
      " · baseline $"+j.record.baseline_price+"/"+j.record.price_unit+
      " (invoice "+j.record.baseline_source_ref+") · "+j.record.horizon_days+
      " days · spike defined as "+j.record.spike_threshold_pct+
      "% or more. "+j.message;
  }catch(e){node.textContent="Could not freeze warning: "+e.message;}
  finally{button.disabled=false;}
}
async function scoreForecasts(){
  const node=byId("forecast-results");
  try{
    const j=await req("/api/pricing/forecasts");clear(node);
    node.append(el("strong",j.evaluated+" comparable invoice outcomes · "+
      j.pending+" pending · "+j.unobserved+" no matching future invoice"));
    node.append(el("p","Correct "+j.correct+" / "+j.evaluated+
      " · warning accuracy "+(j.accuracy===null?"N/A":j.accuracy+"%")+
      " · always-no-spike baseline "+(j.always_no_spike_baseline_accuracy===null?"N/A":
      j.always_no_spike_baseline_accuracy+"%")));
    for(const x of j.samples.slice(0,12))
      node.append(el("div",x.material_key+" · "+x.risk+" · "+
        x.status+(x.change_pct===null?"":" · actual change "+x.change_pct+"%")+
        (x.outcome_invoice?" · "+x.outcome_invoice.source_ref:""),"record"));
    node.append(el("p",j.disclaimer));
  }catch(e){node.textContent="Evaluation failed: "+e.message;}
}
async function journalForecastScorecard(){
  const node=byId("forecast-results");
  try{
    const j=await req("/api/bean/forecast-outcomes",{method:"POST"});
    node.append(el("p",j.journal.connected?"BEAN Core recorded scorecard event "+
      j.journal.event_id+". This does not train or validate a model.":
      "BEAN Core not connected: "+j.journal.reason));
  }catch(e){node.append(el("p","Cannot journal scorecard: "+e.message));}
}


function prSelectedRequest(result){
  const row=result.request||result;
  byId("pr-request-id").value=row.request_id;
  byId("pr-approve").disabled=row.status!=="draft";
  byId("pr-dispatch").disabled=row.status!=="approved";
  const area=byId("pr-draft-result");clear(area);
  area.append(el("strong",row.request_id+" · "+row.status.toUpperCase()));
  area.append(el("p","Source digest: "+row.payload_sha256));
  for(const line of row.payload.lines)
    area.append(el("div",line.material_key+" · "+line.quantity+" "+line.unit+
      (line.job?" · job "+line.job:"")+
      (line.needed_by?" · need "+line.needed_by:"")+
      (line.source_ref?" · "+line.source_ref:""),"record"));
  area.append(el("p","Justification: "+row.payload.justification));
}
function prInput(){
  return {requested_by:byId("pr-requestor").value.trim(),
    department:byId("pr-department").value.trim(),
    justification:byId("pr-justification").value.trim(),
    source_system:"EZstimate",
    lines:[{
      material_key:byId("pr-material").value.trim(),
      quantity:byId("pr-quantity").value,
      unit:byId("pr-unit").value,
      needed_by:byId("pr-need-date").value,
      job:byId("pr-job").value.trim(),
      supplier_preference:byId("pr-supplier").value.trim(),
      source_ref:byId("pr-source-ref").value.trim(),
      description:byId("pr-description").value.trim()
    }]};
}
function prUseMaterial(){
  byId("pr-material").value=byId("price-key").value;
  byId("pr-quantity").value=byId("price-qty").value||"1";
  byId("pr-unit").value=byId("price-unit").value;
  byId("pr-supplier").value=byId("price-supplier").value;
  byId("pr-source-ref").value=byId("price-source-ref").value;
  byId("pr-draft-result").textContent="Material details copied. Review quantity and purchasing unit, then create the request.";
}
async function prConnectorStatus(){
  try{
    const config=await req("/api/procurement/status");
    byId("pr-connector").textContent="Approval credential "+(config.approval_configured?"configured":"not configured")+
      " · ERP transport "+config.dispatch_mode+
      (config.auto_dispatch_after_approval?" · sends after approval":" · no outbound connector")+
      ". Server configuration is required before live dispatch.";
  }catch(e){byId("pr-connector").textContent="Purchasing connector unavailable: "+e.message;}
}
async function prCreate(){
  const button=byId("pr-create");button.disabled=true;
  try{
    const result=await req("/api/procurement/requests",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(prInput())});
    prSelectedRequest(result);
    byId("pr-delivery").textContent="Draft saved; no purchase request has been sent.";
  }catch(e){byId("pr-draft-result").textContent="Cannot draft: "+e.message;}
  finally{button.disabled=false;}
}
async function prApprove(){
  const id=byId("pr-request-id").value,credential=byId("pr-approval-token").value,
    actor=byId("pr-approver").value.trim(),button=byId("pr-approve");
  if(!id||!actor||!credential){byId("pr-delivery").textContent="Request, approver and approval credential are required.";return;}
  button.disabled=true;
  try{
    const result=await req("/api/procurement/requests/"+encodeURIComponent(id)+"/approve",{
      method:"POST",headers:{"Content-Type":"application/json",
        "X-EZstimate-Approval-Token":credential},
      body:JSON.stringify({approver:actor})});
    prSelectedRequest(result);
    byId("pr-delivery").textContent=result.message+" · Status: "+result.request.status+
      (result.delivery?" · "+result.delivery.message:"");
  }catch(e){byId("pr-delivery").textContent="Approval failed: "+e.message;}
  finally{byId("pr-approval-token").value="";await prConnectorStatus();}
}
async function prDispatch(){
  const id=byId("pr-request-id").value,credential=byId("pr-approval-token").value;
  if(!id||!credential){byId("pr-delivery").textContent="Select an approved request and supply approval credential.";return;}
  byId("pr-dispatch").disabled=true;
  try{
    const result=await req("/api/procurement/requests/"+encodeURIComponent(id)+"/dispatch",{
      method:"POST",headers:{"X-EZstimate-Approval-Token":credential}});
    prSelectedRequest(result);
    byId("pr-delivery").textContent=(result.duplicate?"Already dispatched. ":"")+
      "Status: "+result.request.status+" · "+
      (result.request.delivery_receipt?result.request.delivery_receipt.message:"No receipt");
  }catch(e){
    byId("pr-delivery").textContent="Dispatch not confirmed: "+e.message+
      ". Check the request history before any retry.";
    try{prSelectedRequest((await req("/api/procurement/requests/"+encodeURIComponent(id))).request);}
    catch(ignore){}
  }finally{byId("pr-approval-token").value="";}
}
async function prList(){
  try{
    const response=await req("/api/procurement/requests");
    const target=byId("pr-draft-result");clear(target);
    target.append(el("strong",response.requests.length+" recent purchase requests"));
    for(const request of response.requests){
      const button=el("button",request.request_id+" · "+request.status+
        " · "+request.payload.lines.length+" line(s)","secondary");
      button.type="button";button.addEventListener("click",()=>{
        prSelectedRequest(request);byId("pr-delivery").textContent=
          "Selected existing request. Check status before approval or dispatch.";
      });
      const container=el("div",null,"record");container.append(button);
      target.append(container);
    }
  }catch(e){byId("pr-draft-result").textContent="Request list unavailable: "+e.message;}
}

const today=new Date().toISOString().slice(0,10);
byId("price-date").value=today;byId("market-date").value=today;
byId("save-price").addEventListener("click",saveObservedPrice);
byId("find-price").addEventListener("click",loadHistoricalPrices);
byId("price-line").addEventListener("change",()=>{byId("apply-price").disabled=
  !(st.priceCandidate&&st.priceCandidate.price_unit==="ea"&&byId("price-line").value!=="");});
byId("apply-price").addEventListener("click",applyHistoryToLine);
byId("save-signal").addEventListener("click",saveSignal);
byId("assess-pressure").addEventListener("click",assessPressure);
byId("market-bean").addEventListener("click",journalPressure);
byId("mid-preview").addEventListener("click",previewMidWorkbook);
byId("sync-official").addEventListener("click",refreshOfficialFeeds);
byId("freeze-forecast").addEventListener("click",freezePriceForecast);
byId("score-forecasts").addEventListener("click",scoreForecasts);
byId("journal-scorecard").addEventListener("click",journalForecastScorecard);
byId("pr-from-price").addEventListener("click",prUseMaterial);
byId("pr-create").addEventListener("click",prCreate);
byId("pr-approve").addEventListener("click",prApprove);
byId("pr-dispatch").addEventListener("click",prDispatch);
byId("pr-list").addEventListener("click",prList);
prConnectorStatus();

core();
