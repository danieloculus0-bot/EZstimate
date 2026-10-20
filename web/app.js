"use strict";
// EZstimate browser client, backed by local Python quote engine.
const st={documents:[],issues:[],rows:[],quote:null,bean:null};
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
core();
