/*
 * EZstimate browser engineering engine.
 * Deterministic source-candidate extraction and cost arithmetic.
 * No BEAN Core, LLM, server upload or vendor pricing in this module.
 */

const MATERIALS = [
  ["ASTM A36", /\b(?:ASTM\s*)?A[\s-]?36\b/i],
  ["ASTM A572 GR 50", /\bA572(?:\s*(?:GR|GRADE)\.?\s*50)?\b/i],
  ["1018 steel", /\b(?:AISI\s*)?1018\b/i],
  ["304 stainless", /\b(?:(?:SS|STAINLESS)\s*304|304\s*(?:SS|STAINLESS))\b/i],
  ["316 stainless", /\b(?:(?:SS|STAINLESS)\s*316|316\s*(?:SS|STAINLESS))\b/i],
  ["5052-H32 aluminum", /\b5052[\s-]*H32\b/i],
  ["6061-T6 aluminum", /\b6061[\s-]*T6\b/i],
  ["HRPO steel", /\bHRPO\b/i],
  ["CRS", /\bCRS\b/i],
  ["HRS", /\bHRS\b/i],
];
const PATTERNS = {
  part: /\b(?:PART\s*(?:NO\.?|NUMBER|#)|P\/N|DRAWING\s*(?:NO\.?|#)|DWG\s*(?:NO\.?|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})/i,
  rev: /\bREV(?:ISION)?\s*[:#-]?\s*([A-Z0-9]{1,3})\b/i,
  qty: /\b(?:QTY|QUANTITY)\s*[:#-]?\s*(\d{1,7})\b/i,
  po: /\b(?:PURCHASE\s*ORDER|P\.?O\.?)\s*(?:NUMBER|NO\.?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{2,})/i,
  terms: /\b(NET\s*(?:15|30|45|60|90)|DUE\s+ON\s+RECEIPT|PREPAID)\b/i,
  due: /\b(?:DUE\s*DATE|REQUIRED\s*(?:BY|DATE)|DELIVERY\s*DATE|SHIP\s*BY)\s*[:#]?\s*([0-9]{1,4}[\/-][0-9]{1,2}[\/-][0-9]{2,4})/i,
};
const PROCESSES = {
  cutting: /\b(?:LASER|PLASMA|WATERJET|CUTTING)\b/i,
  forming: /\b(?:FORM|BEND|BRAKE)\b/i,
  welding: /\b(?:WELD|GMAW|GTAW|MIG|TIG)\b/i,
  machining: /\b(?:MACHIN(?:E|ING)|MILL|DRILL|REAM|TAP)\b/i,
  finishing: /\b(?:POWDER\s*COAT|ANODIZ|PLAT(?:E|ING)|PAINT)\b/i,
};

function candidate(value, doc, region) {
  return {value: String(value).trim(), source: doc, page: region.page ?? null,
    region: region.area ?? "text", status: "proposed"};
}
function getCandidate(regions, pattern, filename) {
  for (const region of regions) {
    const match = region.text.match(pattern);
    if (match) return candidate(match[1] ?? match[0], filename, region);
  }
  return null;
}
function guessMaterial(regions, filename) {
  for (const region of regions) {
    const lines = region.text.split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      let match = lines[i].match(/^\s*MATERIAL(?:\s*SPEC(?:IFICATION)?)?\s*[:=\-]\s*(.+)$/i);
      let raw = match?.[1]?.trim();
      if (!raw && /^\s*MATERIAL\s*:?\s*$/i.test(lines[i])) raw = lines[i+1]?.trim();
      if (raw && raw.length <= 90 && !/^SEE\s+(?:NOTE|DRAWING)/i.test(raw))
        return candidate(raw, filename, region);
    }
  }
  for (const region of regions) {
    for (const [name, pattern] of MATERIALS) {
      if (pattern.test(region.text)) return candidate(name, filename, region);
    }
  }
  return null;
}
export function analyzeText(filename, text, extraRegions = []) {
  const body = String(text ?? "");
  const regions = [...extraRegions, {text:body, area:"whole document"}]
    .filter(x => x.text?.trim());
  const looksPo = /\bPURCHASE\s*ORDER\b|\bP\.?O\.?\s*(?:NO|NUMBER|#)\b/i.test(body);
  const fields = {};
  for (const [field, pattern] of Object.entries(PATTERNS)) {
    if (field === "po" || field === "terms" || field === "due") {
      if (!looksPo) continue;
    }
    const value = getCandidate(regions, pattern, filename);
    if (value) fields[field] = value;
  }
  const material = guessMaterial(regions, filename);
  if (material) fields.material = material;
  const processes = Object.entries(PROCESSES)
    .filter(([, pattern]) => pattern.test(body)).map(([name]) => name);
  const warnings = [];
  if (!body.trim()) warnings.push("No selectable text. Image-only PDFs need OCR, which is not in this demo.");
  if (!looksPo && !fields.material) warnings.push("Material grade not found. Verify the material and stock form.");
  if (!fields.part) warnings.push("Part number not found.");
  return {
    filename, kind: looksPo ? "purchase_order" : "drawing",
    fields, bom: [], processes, warnings
  };
}
export function parseCSV(filename, input) {
  const text = String(input).replace(/^\uFEFF/, "");
  const rows = []; let row = [], value = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i+1] === '"') {value += '"'; i++;}
      else quoted = !quoted;
    } else if (c === "," && !quoted) {row.push(value); value = "";}
    else if ((c === "\n" || c === "\r") && !quoted) {
      if (c === "\r" && text[i+1] === "\n") i++;
      row.push(value); rows.push(row); row = []; value = "";
    } else value += c;
  }
  if (quoted) throw new Error("CSV has an unterminated quoted field");
  if (value || row.length) {row.push(value); rows.push(row);}
  if (!rows.length) throw new Error("Empty BOM CSV");
  const norm = x => String(x ?? "").trim().toLowerCase().replace(/[^a-z0-9]/g,"");
  const headers = rows[0].map(norm);
  const column = (...aliases) => headers.findIndex(h => aliases.includes(h));
  const partIndex = column("part", "partnumber", "partno", "pn", "itemnumber", "component");
  const qtyIndex = column("qty", "quantity", "count", "requiredqty");
  const descIndex = column("description", "desc", "name");
  const matIndex = column("material", "materialspec", "grade");
  const revIndex = column("rev", "revision");
  if (partIndex < 0 || qtyIndex < 0) throw new Error("BOM needs Part Number and Qty columns");
  const bom = [];
  for (let i = 1; i < rows.length; i++) {
    const cell = col => col >= 0 ? String(rows[i][col] ?? "").trim() : "";
    const part = cell(partIndex);
    const quantity = Number(cell(qtyIndex));
    if (!part && !cell(qtyIndex)) continue;
    if (!part || !Number.isSafeInteger(quantity) || quantity <= 0) continue;
    bom.push({part, qty: quantity, description:cell(descIndex), material:cell(matIndex),
      rev:cell(revIndex), source:filename, row:i+1, status:"proposed"});
  }
  return {filename, kind:"bom", fields:{}, bom, processes:[],
    warnings:bom.length ? [] : ["No valid BOM rows with part and positive integer quantity found."]};
}
export function reviewDocuments(documents) {
  const issues = [];
  for (const doc of documents) {
    for (const message of doc.warnings ?? [])
      issues.push({level:"review", message, source:doc.filename});
  }
  const fields = new Map();
  for (const doc of documents) {
    if (doc.kind === "bom") continue;
    for (const key of ["part","rev","material","qty"]) {
      const field = doc.fields[key];
      if (field?.value) {
        if (!fields.has(key)) fields.set(key, []);
        fields.get(key).push({value:String(field.value).trim(), source:doc.filename});
      }
    }
  }
  for (const [key, variants] of fields) {
    if (new Set(variants.map(x => x.value.toLowerCase())).size > 1)
      issues.push({level:"conflict",message:"Conflicting " + ({part:"part numbers",rev:"drawing revisions",
        material:"material specifications",qty:"quantities"}[key] || key),
        source:variants.map(x=>x.source).join(" / ")});
  }
  const drawings = documents.filter(x=>x.kind==="drawing");
  const pos = documents.filter(x=>x.kind==="purchase_order");
  if (!pos.length) issues.push({level:"info", message:"No purchase order supplied. Commercial terms unverified.", source:"package"});
  if (!drawings.length) issues.push({level:"info", message:"No drawing supplied. Material and manufacturing requirements unverified.", source:"package"});
  return issues;
}
export function seedLines(documents, previous = []) {
  const old = new Map(previous.map(x=>[x.part,x]));
  const bom = documents.flatMap(x=>x.bom ?? []);
  const partRows = bom.length ? bom : documents.filter(x=>x.kind==="drawing" && x.fields?.part)
    .map(x=>({part:x.fields.part.value, qty: Number(x.fields.qty?.value) || 1,
      material:x.fields.material?.value || "", rev:x.fields.rev?.value || "", source:x.filename}));
  const poByPart = new Map(documents.filter(x=>x.kind==="purchase_order" && x.fields.part)
    .map(x=>[x.fields.part.value, x]));
  const unique = new Map();
  for (const item of partRows) {
    if (!item.part) continue;
    if (unique.has(item.part)) continue;
    const po = poByPart.get(item.part);
    const restored = old.get(item.part) || {};
    unique.set(item.part, {
      part:item.part, qty:restored.qty ?? (po?.fields.qty?.value ? Number(po.fields.qty.value) : item.qty),
      material:item.material || "", source:item.source,
      materialCost: restored.materialCost ?? "", laborHours:restored.laborHours ?? "",
      shopRate:restored.shopRate ?? "", outside:restored.outside ?? "",
      setup:restored.setup ?? "", scrap:restored.scrap ?? "", margin:restored.margin ?? ""
    });
  }
  return Array.from(unique.values());
}
const needed = ["materialCost","laborHours","shopRate","outside","setup","scrap","margin"];
export function calculate(lines) {
  if (!Array.isArray(lines) || !lines.length)
    return {status:"incomplete", total:null, items:[], errors:["Add at least one part and its costs."]};
  const errors = [], items = []; let grand = 0;
  lines.forEach((line, index) => {
    const missing = needed.filter(k => String(line[k] ?? "").trim() === "");
    const qty = Number(line.qty);
    if (missing.length) {
      errors.push((line.part || "Line " + (index+1)) + ": missing " + missing.join(", "));
      items.push({part:line.part, extended:null, error:"Missing inputs"}); return;
    }
    const nums = Object.fromEntries(needed.map(k => [k, Number(line[k])]));
    if (!Number.isSafeInteger(qty) || qty <= 0 ||
      needed.some(k => !Number.isFinite(nums[k]) || nums[k] < 0) ||
      nums.scrap > 100 || nums.margin >= 100) {
      errors.push((line.part || "Line " + (index+1)) + ": invalid quantity, cost, scrap or margin");
      items.push({part:line.part,extended:null,error:"Invalid inputs"});return;
    }
    const material = nums.materialCost * (1 + nums.scrap/100);
    const unitCost = material + nums.laborHours * nums.shopRate + nums.outside;
    const extendedCost = unitCost * qty + nums.setup;
    const extended = extendedCost / (1 - nums.margin/100);
    if (!Number.isFinite(extended)) {
      errors.push((line.part || "Line " + (index+1)) + ": arithmetic overflow");
      items.push({part:line.part,extended:null,error:"Invalid total"});return;
    }
    grand += extended;
    items.push({part:line.part, qty,unit:extended/qty, extended,
      manufacturing:extendedCost,source:line.source});
  });
  return {status:errors.length?"incomplete":"draft_review",total:errors.length?null:grand,
    items, errors, approval:"not approved", tax:null, freight:null};
}
export function localAdvisory(documents, lines, quote) {
  const notes = reviewDocuments(documents).filter(x=>x.level==="conflict").map(x=>x.message + ". Resolve before issuing a quote.");
  if (!documents.some(x=>x.fields?.material || x.bom?.some(b=>b.material)))
    notes.push("No sourced material specification. Confirm grade, stock form and thickness.");
  if (!documents.some(x=>x.fields?.rev || x.bom?.some(b=>b.rev)))
    notes.push("No verified drawing revision. Confirm against the current controlled file.");
  if (quote.status === "incomplete") notes.push("Cost build is incomplete. No reliable sell total is available.");
  if (documents.some(x=>x.processes?.includes("welding")))
    notes.push("Welding noted. Confirm weld size/length, fixture and inspection labor against the routing.");
  if (documents.some(x=>x.processes?.includes("finishing")))
    notes.push("Finish operation noted. Verify pretreatment, masking, coating area and outside service requirements.");
  if (!documents.some(x=>x.kind==="purchase_order"))
    notes.push("No PO on file. Verify lead time, requested delivery, shipment and commercial terms.");
  if (!notes.length) notes.push("Basic source and arithmetic checks completed. Review manufacturing assumptions and approval before release.");
  return {origin:"EZstimate local deterministic checks",beanCoreInvoked:false,notes};
}
export const synthetic = {
  drawing: "DRAWING NO: EZ-1042\nPART NO: EZ-1042\nREV: C\nMATERIAL: ASTM A36\nTHICKNESS: .188\nQTY: 25\nNOTES: LASER CUT, FORM 90 DEG, WELD, POWDER COAT. VERIFY COSMETIC CRITERIA.",
  po: "PURCHASE ORDER: PO-60291\nPART NO: EZ-1042\nREV: B\nQTY: 25\nNET 30\nSHIP BY: 11/15/2026\nFOB ROCHESTER",
  csv: "Part Number,Qty,Description,Material,Rev\nEZ-1042,25,Formed bracket,ASTM A36,C",
  costs: {materialCost:"8.40",laborHours:"0.45",shopRate:"78",outside:"3.75",
    setup:"45",scrap:"8",margin:"24"}
};
