import test from "node:test";
import assert from "node:assert/strict";
import {analyzeText,parseCSV,reviewDocuments,seedLines,calculate,localAdvisory,synthetic} from "../web/engine.mjs";

test("extracts source-referenced drawing material and revision",()=>{
  const doc=analyzeText("drawing.pdf",synthetic.drawing,[{text:"MATERIAL: ASTM A36\nREV: C",page:1,area:"lower-right title block"}]);
  assert.equal(doc.fields.material.value,"ASTM A36");
  assert.equal(doc.fields.material.region,"lower-right title block");
  assert.equal(doc.fields.rev.value,"C");
});
test("imports BOM rows and preserves source row",()=>{
  const bom=parseCSV("bom.csv",synthetic.csv);
  assert.equal(bom.bom[0].qty,25);
  assert.equal(bom.bom[0].row,2);
  assert.equal(bom.bom[0].material,"ASTM A36");
});
test("detects revision conflict across PO and drawing",()=>{
  const documents=[analyzeText("drawing.pdf",synthetic.drawing),
    analyzeText("purchase_order.pdf",synthetic.po),parseCSV("bom.csv",synthetic.csv)];
  assert.ok(reviewDocuments(documents).some(x=>x.level==="conflict"&&x.message.includes("revisions")));
});
test("computes real draft quote from explicit synthetic costs",()=>{
  const docs=[analyzeText("drawing.pdf",synthetic.drawing),parseCSV("bom.csv",synthetic.csv)];
  const [line]=seedLines(docs);
  const result=calculate([{...line,...synthetic.costs}]);
  assert.equal(result.status,"draft_review");
  assert.ok(result.total>0);
  assert.equal(result.items[0].qty,25);
});
test("never returns partial total when cost missing, invalid, or margin 100",()=>{
  const base={part:"X",qty:5,...synthetic.costs};
  for(const change of [{materialCost:""},{qty:0},{margin:"100"},{materialCost:"NaN"}]){
    const result=calculate([{...base,...change}]);
    assert.equal(result.status,"incomplete");
    assert.equal(result.total,null);
  }
});
test("local adviser never impersonates BEAN Core",()=>{
  const info=localAdvisory([],[],calculate([]));
  assert.equal(info.beanCoreInvoked,false);
  assert.match(info.origin,/local deterministic/);
});
