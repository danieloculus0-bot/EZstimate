# Material Forecast and price memory integration (alpha)

This is the next module inside EZstimate, not a second disconnected estimate calculator.

## What's implemented

- `ezstimate/pricing.py` persists real, dated purchasing price observations to **local SQLite** by exact ERP material key, original quote/PO/invoice reference, supplier, source quantity, date, currency and price unit.
- Source records are explicitly entered or imported by a trusted local operator. Missing cost remains missing. A supplier price, an estimated material allowance and a commodity indicator are distinct kinds of evidence.
- The local workbench has Price Memory and Material Market Watch panels.
- A retrieved cost does **not** modify an estimate. The operator can explicitly apply an **ea** price to a quote line, with the source retained. Sheet, lb and ft cannot be used as per-part costs without calculating a verified conversion/yield.
- Five input series are available for manual observation: diesel USD/gal, steel market index, aluminum market index, supplier lead time in days and sentiment score 0-100.
- The pressure-watch logic compares dated values. Significant upward movement results in transparent points and an **elevated/high** watch. Missing history produces **insufficient**, not an invented zero or a confident prediction. Readings over 90 days old do not contribute pressure points.
- With a real optional BEAN Core connection, the market assessment can be journaled as a source-backed observation. This invokes BEAN's actual persistence interface. It is **not** proof of model inference, self-learning, validated spike prediction, or automatic price approval.
- Windows/Linux tests exercise history persistence, source collisions, material/unit matching, market-risk labels, Flask integration and missing-BEAN behavior.

## Run locally

```powershell
git clone https://github.com/danieloculus0-bot/EZstimate.git
cd EZstimate
py -m pip install -e .
py -m ezstimate.server
```

Open http://127.0.0.1:8765 and use **04 Price Memory**. The SQLite database lives by default at `~/.ezstimate/price_memory.sqlite3`, or set `EZSTIMATE_PRICE_DB` to a different local file path. Keep this database under your own access permissions and backup plan; **never check it or real supplier prices into the public repository**.

Example API call to store a *fictional* dated invoice price (PowerShell):

```powershell
$body = @{
  material_key="SHT-STL-0250X60X120-A36-HR";supplier="Example Metals";
  source_type="invoice";source_ref="INV-DEMO-001";effective_date="2026-01-15";
  unit_price="220.25";price_unit="sheet";quantity="12";currency="USD"
} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8765/api/pricing/prices -Method POST -ContentType application/json -Body $body
```

`GET /api/pricing/prices?material_key=...&price_unit=sheet` returns source-identified history and the newest candidate for human review. `GET /api/pricing/pressure?family=steel` reports the signal history and transparent watch points.

## Reuse of the earlier Material Intelligence Dashboard (MID)

MID already contained the correct operational entities: normalized material keys, shortage quantity and value, forecast need windows, job due dates, supplier lead times, PO commitments and market pressure. EZstimate should reuse this **data contract** rather than trying to treat every spreadsheet field as a historical purchasing price.

| MID field family | EZstimate responsibility | Avoid |
| --- | --- | --- |
| Material part / normalized key / grade / shape | Exact lookup key and supported normalized catalog metadata | Treating A36 alone as a unique purchasable item |
| Job, customer, part, due date / need window | Quote demand and timing, linked to Axiom | Confusing an assembly BOM with purchased stock |
| On hand / on order / needed / adjusted balance | Purchasing exposure signal | Assuming a positive forecast balance is a guaranteed available allocation |
| Unit cost, supplier, PO or invoice | Historical price only when dated, sourced, with known unit and actual supplier evidence | Treating an unknown import cost as an invoice |
| Lead time, promised receipt and market indicators | Material supply/price-pressure watch, with dated evidence | Inflating a quote automatically |
| Forecast action / owner / review date | Review work queue | Equating a heuristic with a supplier-confirmed commitment |

The first versioned MID **XLSX read-only adapter** is now available at \`/api/pricing/mid-preview\` with a companion file picker in the local interface. It recognizes JobBOSS demand events, risk-register rows, and buyer action queues while retaining sheet/row source evidence. It does not automatically import MID forecast records into the persistent pricing database or change Axiom's released estimate. Expanded column/unit verification and sustained forecast snapshots are still planned.

## BEAN learning loop (next increment)

1. Retain a dated material/supplier baseline purchase price and proposed risk hypothesis.
2. When a later purchase price arrives, compare **matching material code, unit, quantity break and supplier** against the baseline.
3. Track separate errors by material family and signal combination with controls for market regime and date. Publish both hits and misses to BEAN Core.
4. Promote a forecasting rule only when its improvement over a simple historical baseline is demonstrated on holdout periods.
5. Let BEAN propose a reserve or re-quote warning, but leave the estimator's entered cost and final quote authorization unchanged unless the operator elects a change.

## Live data integration (not yet implemented)

A future approved adapter can retrieve public diesel and commodity producer-price series from documented, licensed sources (such as EIA and BLS/FRED), recording provider, series ID, publication date, unit, timestamp and cache freshness. Sources are not one-to-one predictors of fabrication stock costs. Sector news and sentiment need a documented scoring method plus attribution before they are promoted into a quantitative feature. Supplier lead times and local surcharges still require purchasing data.

**GitHub Pages** serves the stand-alone, browser-side estimate demo. It has no local SQLite or BEAN Core process. The persistent Price Memory workbench runs in the **Python local build** only.

## Official market data refresh and invoice feedback (October 2026)

**Implemented in the local Python service, not in the static Pages demo.**

- `ezstimate/market_feeds.py` reads official **BLS PPI steel mill products WPU1017**, **BLS PPI aluminum mill shapes WPU102501**, and **EIA weekly US No. 2 retail diesel EMD_EPD2D_PTE_NUS_DPG**. The BLS public GET does not need a registration key; EIA requires a free personal API key from https://www.eia.gov/opendata/register.php.
- `ezstimate/auto_refresh.py` refreshes at server start and every **24 hours while the local server is running**, unless `EZSTIMATE_MARKET_AUTO_REFRESH=0`. The local page also has an explicit **Refresh EIA / BLS data** button. The service does *not* refresh if the computer/server is off, and no GitHub Pages scheduler can reach the private local database.
- Both sources are recorded with observed date, value, official series ID and units in the local database. Duplicates do not create new records. If a provider revises an earlier period, the original observation is **not silently overwritten**; the refresh reports a revision conflict for review.
- The BLS PPI is a **monthly index**, not dollars per sheet or per pound. EIA diesel is weekly **USD/gallon**, not a quote from a fuel supplier. No public index is treated as an actual supplier material price.
- A missing `EIA_API_KEY` produces `not_configured`, not a fake diesel price or a blocked BLS refresh. A provider outage produces a visible partial/error state, retaining earlier data.

### Start with automatic updates

```powershell
cd EZstimate
$env:EIA_API_KEY = Read-Host "Enter your free EIA API key"
py -m ezstimate.server
```

The key stays in your current PowerShell environment and is not returned to the browser in status responses. Without it, the local app still refreshes BLS steel and aluminum. Avoid committing keys to GitHub or saving them inside client-side JavaScript. Set `$env:EZSTIMATE_MARKET_AUTO_REFRESH="0"` to disable the periodic task if needed.

### Frozen BEAN feedback scorecard

- `POST /api/pricing/forecasts` freezes a **dated pressure hypothesis** based on the material family, source-linked invoice baseline, exact material code, supplier, original buying quantity/unit, horizon (7-365 days), and percentage spike threshold. The local UI has a **Freeze warning** button. The API does not accept a backdated prediction date.
- `GET /api/pricing/forecasts` evaluates matured hypotheses against **later-entered, post-hypothesis invoices** with the same material key, supplier, price unit and quantity. The future invoice effective date must be inside the horizon. A forecast is **pending** until horizon end, or **unobserved** if no exact-matching outcome exists.
- Descriptive accuracy is compared with a simple **always no-spike** baseline on the *same observed cases*, exposing sample counts, misses and incomplete evidence. Empty histories are not scored. This is *not* a statistically validated predictive advantage.
- `POST /api/bean/forecast-outcomes` can optionally record those source-grounded scores to real installed BEAN Core. This currently creates evidence events, **not a trained model, autonomous decision, price escalation or backtested claim**.
- No actual customer prices, API keys or supplier documents are included in CI. Offline tests use mocked provider payloads and synthetic invoices across Linux and Windows.

The next research task is an adequately powered, holdout-tested policy that predicts subsequent invoice outcomes better than a simple baseline **without hindsight**. BEAN may propose rule changes; the source-linked results determine whether they actually improve.
