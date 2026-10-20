import {analyzeText,parseCSV,reviewDocuments,seedLines,calculate,localAdvisory,synthetic} from "./engine.mjs";

// Functional browser-only estimating demo. BEAN Core is not invoked here.
const st={documents:[],lines:[],quote:null,pasteIndex:0};
const $=id=>document.getElementById(id);
const make=(tag,txt,cls)=>{
  const node=document.createElement(tag);
  if(txt!==undefined&&txt!==null)node.textContent=String(txt);
  if(cls)node.className=cls;
  return node;
};
const clean=node=>node.replaceChildren();
const usd=value=>Number.isFinite(value)?new Intl.NumberFormat("en-US",{style:"currency",currency:"USD"}).format(value):"N/A";
const source=field=>(field.source||"manual")+(field.page?" · p"+field.page:"")+(field.region?" · "+field.region:"")+(field.row?" · row "+field.row:"");
function message(text,error=false){$("message").textContent=text;$("message").className="notice"+(error?" error":"");}
function invalidate(){
  st.quote=null;$("export").disabled=true;$("total").textContent="N/A";
  $("quote-status").textContent="Inputs changed. Recalculate draft.";
  clean($("quote-details"));
}
function counters(issues){
  $("documentsCount").textContent=st.documents.length;
  $("partsCount").textContent=st.lines.length;
  $("flagsCount").textContent=issues.filter(i=>i.level!=="info").length;
}
function renderDocs(){
  const holder=$("documents");clean(holder);
  if(!st.documents.length){holder.append(make("p","No documents loaded."));return;}
  st.documents.forEach((doc,index)=>{
    const card=make("div",null,"file-record");
    card.append(make("strong",doc.filename+" · "+doc.kind.replaceAll("_"," ")));
    const grid=make("div",null,"meta");
    for(const [key,field] of Object.entries(doc.fields||{})){
      grid.append(make("span",key.replaceAll("_"," ")));
      const wrap=make("div");const inp=make("input");
      inp.type="text";inp.value=field.value;inp.setAttribute("aria-label",key+" in "+doc.filename);
      inp.addEventListener("change",()=>{
        field.value=inp.value.trim();field.status="edited";
        st.lines=seedLines(st.documents,st.lines);
        invalidate();renderAll();
        message("Candidate field corrected. Review the original source before approval.");
      });
      wrap.append(inp);wrap.append(make("small",source(field)+" · "+(field.status==="edited"?"edited":"proposed")));
      grid.append(wrap);
    }
    if(Object.keys(doc.fields||{}).length)card.append(grid);
    if(doc.bom?.length){
      card.append(make("div",doc.bom.length+" BOM rows recognized.","source-note"));
      for(const row of doc.bom.slice(0,8))
        card.append(make("small",row.part+" × "+row.qty+(row.material?" · "+row.material:"")+" · "+source(row)));
    }
    if(doc.processes?.length)card.append(make("small","Process clues: "+doc.processes.join(", ")+" (unverified)"));
    if(doc.warnings?.length)for(const text of doc.warnings)card.append(make("small","Review: "+text));
    holder.append(card);
  });
}
function renderFlags(issues){
  const holder=$("exceptions");clean(holder);
  if(!issues.length){holder.append(make("p","No rule-based conflicts detected. Manual review still required."));return;}
  for(const issue of issues){
    const card=make("div",issue.message,"record warning "+issue.level);
    card.append(make("small",issue.source||"package"));holder.append(card);
  }
}
const cols=[
 ["part","Part"],["qty","Quantity"],["materialCost","Material cost"],["laborHours","Labor hours"],
 ["shopRate","Shop rate"],["outside","Outside cost"],["setup","Setup cost"],["scrap","Scrap percent"],["margin","Margin percent"]
];
function renderLines(){
  const holder=$("lines");clean(holder);
  if(!st.lines.length){
    const row=make("tr"),cell=make("td","No line items. Add a line or import a BOM.");cell.colSpan=10;
    row.append(cell);holder.append(row);return;
  }
  st.lines.forEach((item,index)=>{
    const tr=make("tr");
    for(const [key,label] of cols){
      const td=make("td"),inp=make("input");
      inp.className=key==="part"?"part":"";
      if(key!=="part"){inp.type="number";inp.min="0";inp.step=key==="qty"?"1":"any";}
      inp.value=item[key]??"";
      inp.setAttribute("aria-label",label+" on line "+(index+1));
      inp.addEventListener("input",()=>{item[key]=inp.value;invalidate();});
      td.append(inp);
      if(key==="part")td.append(make("small",item.source||"manual"));
      tr.append(td);
    }
    tr.append(make("td","Not calculated","sell"));holder.append(tr);
  });
}
function renderBean(){
  const result=localAdvisory(st.documents,st.lines,calculate(st.lines));
  const box=$("bean-findings");clean(box);
  if(!st.documents.length&&!st.lines.length){box.append(make("p","Load documents to inspect source and process assumptions."));return;}
  for(const finding of result.notes)box.append(make("div",finding,"advice"));
  box.append(make("small","EZstimate local deterministic reviewer, not BEAN Core."));
}
function renderAll(){
  const issues=reviewDocuments(st.documents);
  counters(issues);renderDocs();renderFlags(issues);renderLines();renderBean();
}
function sample(){
  st.documents=[
    analyzeText("DEMO_DWG_EZ-1042.txt",synthetic.drawing),
    analyzeText("DEMO_PO-60291.txt",synthetic.po),
    parseCSV("DEMO_BOM.csv",synthetic.csv)
  ];
  st.lines=seedLines(st.documents).map(line=>({...line,...synthetic.costs}));
  invalidate();renderAll();
  message("Synthetic RFQ loaded. The drawing is Rev C and the PO is Rev B. Review the mismatch, then calculate.");
}
function reset(){
  st.documents=[];st.lines=[];st.pasteIndex=0;$("files").value="";$("pasteText").value="";
  invalidate();renderAll();message("Workspace cleared. No browser files were saved.");
}
function addLine(){
  st.lines.push({part:"NEW-"+(st.lines.length+1),qty:1,source:"manual",
    materialCost:"",laborHours:"",shopRate:"",outside:"",setup:"",scrap:"",margin:""});
  invalidate();renderAll();message("Added a manual estimate line. Enter costs before calculating.");
}
function compute(){
  const result=calculate(st.lines);st.quote=result;
  $("total").textContent=result.total===null?"N/A":usd(result.total);
  $("quote-status").textContent=result.status==="draft_review"
    ?"Draft calculated · NOT APPROVED":"Incomplete: "+result.errors.slice(0,2).join("; ");
  $("export").disabled=result.status!=="draft_review";
  const detail=$("quote-details");clean(detail);
  for(const item of result.items){
    detail.append(make("div",item.part+" · "+(item.extended===null?"incomplete":usd(item.extended)+" total / "+usd(item.unit)+" each"),"record summary-line"));
  }
  message(result.status==="draft_review"
    ?"Draft calculated from explicit assumptions. Review source conflicts before using it."
    :"Missing or invalid cost inputs. No total issued.",result.status!=="draft_review");
}
function exportDraft(){
  if(!st.quote||st.quote.status!=="draft_review")return;
  const payload={schema:"ezstimate.browser-draft.v1",generated_at:new Date().toISOString(),
    release_status:"DRAFT_NOT_APPROVED",documents:st.documents,source_issues:reviewDocuments(st.documents),
    line_inputs:st.lines,quote:st.quote,
    local_advisory:localAdvisory(st.documents,st.lines,st.quote),
    integration:"browser-only; BEAN Core not invoked"};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}));
  const a=make("a");a.href=url;a.download="EZstimate_DRAFT.json";document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  message("Exported JSON draft. Human verification and approval still required.");
}
function pdfTextLines(tokens){
  const sorted=tokens.filter(t=>t.text).slice().sort((a,b)=>b.y-a.y||a.x-b.x);
  const groups=[];
  for(const token of sorted){
    let group=groups.find(g=>Math.abs(g.y-token.y)<3.5);
    if(!group){group={y:token.y,items:[]};groups.push(group);}
    group.items.push(token);
  }
  return groups.map(g=>g.items.sort((a,b)=>a.x-b.x).map(x=>x.text).join(" ")).join("\n");
}
async function extractPdf(file){
  const pdfjs=await import("https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc="https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.mjs";
  const pdf=await pdfjs.getDocument({data:new Uint8Array(await file.arrayBuffer())}).promise;
  if(pdf.numPages>80){await pdf.destroy();throw Error("PDF exceeds 80-page demo limit");}
  const parts=[],regions=[];
  for(let i=1;i<=pdf.numPages;i++){
    const page=await pdf.getPage(i);
    const viewport=page.getViewport({scale:1});
    const content=await page.getTextContent();
    const tokens=content.items.filter(x=>x.str?.trim()).map(x=>({
      text:x.str.trim(),x:x.transform[4],y:x.transform[5]
    }));
    parts.push(pdfTextLines(tokens));
    regions.push({text:pdfTextLines(tokens.filter(x=>x.x>viewport.width*.48&&x.y<viewport.height*.45)),
      page:i,area:"lower-right title block"});
  }
  await pdf.destroy();
  return {text:parts.join("\n"),regions,pages:parts.length};
}
async function scan(){
  const files=Array.from($("files").files||[]);
  if(!files.length){message("Choose one or more PDF, CSV or TXT files.",true);return;}
  $("scan").disabled=true;
  for(const file of files.slice(0,12)){
    try{
      if(file.size>15*1024*1024)throw Error("File exceeds 15 MB");
      const extension=file.name.split(".").pop().toLowerCase();
      let document;
      if(extension==="pdf"){
        message("Reading selectable PDF text from "+file.name+"...");
        const parsed=await extractPdf(file);
        document=analyzeText(file.name,parsed.text,parsed.regions);
        document.pages=parsed.pages;
      }else if(extension==="csv")document=parseCSV(file.name,await file.text());
      else if(extension==="txt")document=analyzeText(file.name,await file.text());
      else throw Error("Unsupported type. Use PDF, CSV or TXT.");
      st.documents.push(document);
      st.lines=seedLines(st.documents,st.lines);
      invalidate();renderAll();
      message("Analyzed "+file.name+". Confirm detected fields before quoting.");
    }catch(error){message("Could not analyze "+file.name+": "+error.message,true);}
  }
  $("scan").disabled=false;$("files").value="";
}
function paste(){
  let text=$("pasteText").value.trim();
  if(!text){message("Paste drawing or PO text first.",true);return;}
  if($("pasteType").value==="po"&&!/PURCHASE\s*ORDER/i.test(text))text="PURCHASE ORDER\n"+text;
  const name=($("pasteType").value==="po"?"PASTED_PO_":"PASTED_DRAWING_")+(++st.pasteIndex)+".txt";
  st.documents.push(analyzeText(name,text));
  st.lines=seedLines(st.documents,st.lines);
  invalidate();renderAll();message("Text analyzed. Fields remain proposed and require verification.");
}
$("sample").addEventListener("click",sample);
$("clear").addEventListener("click",reset);
$("addline").addEventListener("click",addLine);
$("calculate").addEventListener("click",compute);
$("export").addEventListener("click",exportDraft);
$("scan").addEventListener("click",scan);
$("paste").addEventListener("click",paste);
$("beanReview").addEventListener("click",renderBean);
renderAll();
