---
name: product-review-analyze-skill
description: Mine Amazon product reviews for an ecommerce product keyword. Drives the user's logged-in Chrome via the Claude-in-Chrome MCP to capture top Amazon listings, fetch critical and positive reviews, analyze complaint and praise themes with sales weighting when Helium 10 Xray data is present, and render a static HTML opportunity report.
---

# Product Review Research Procedure

A reusable review-mining workflow for ecommerce sellers. Given a product keyword,
the skill drives the user's logged-in Chrome through the **Claude-in-Chrome MCP**
to find the top Amazon listings, collect their critical and positive reviews, and
write a `reviews.js` data file that a static HTML template renders into a category
opportunity report. It is the review-mining companion to
`product-cost-analyze-for-fba` and mirrors that skill's browser-first, no-fallback
workflow.

## Output files (per run)

All outputs go into a run directory, e.g.
`~/Documents/product-research/<keyword>-reviews/`:

| File | Written by | Description |
|---|---|---|
| `products.json` | Phase 1 | Top-10 Amazon listings, with optional Helium 10 30-day sales |
| `reviews-raw.json` | Phase 2 | Raw critical + positive reviews per ASIN |
| `reviews-map.json` | Phase 3 map | Per-product complaint and praise themes |
| `reviews.js` | Phase 3 reduce | `window.__REVIEW_DATA__ = {...}` — loaded by the template |
| `report.html` | **one-time copy** | Copy of the repo-fetched template, copied and never regenerated |
| `dossier/` | Phase 5 (optional) | Combined Discovery+Cost+Review dossier — reuses the three data files, fetches `dossier.html` |

**This skill is a single file.** A user only needs `SKILL.md`. Two renderers are
fetched from this skill's repo on first run and saved into the run directory:
`report.html` (the review report) and, when the optional Phase 5 runs,
`dossier/dossier.html` (the combined three-phase dossier). Both are static
templates — the HTML is never regenerated, so it costs zero tokens per run.

## Preconditions & setup (read once)

| Requirement | Needed for | Required? |
|---|---|---|
| Chrome + **Claude-in-Chrome MCP** extension, connected | the whole workflow | **Required** |
| **Amazon account, logged in** (same Chrome profile) | review pages are gated behind login | **Required** |
| **Python 3** (or any static server) | serve the report over http in Phase 4 | **Required** |
| **Helium 10** extension + account | Phase 1 Xray market data (30d sales, revenue, BSR, review velocity) + Phase 1.5 Cerebro keyword validation; without it the report degrades to review-only | Recommended |

The skill drives the user's **live Chrome** through the
`mcp__Claude_in_Chrome__*` tools. No automated login or CAPTCHA solving. If
Amazon shows a login wall, CAPTCHA, verification slider, or bot-check in Phase 1
or Phase 2, stop and ask the user to resolve it in Chrome, then continue.

Tools used throughout:
- `list_connected_browsers` / `select_browser` — pick the local Chrome.
- `tabs_context_mcp` with `createIfEmpty: true` — get and reuse a working tab.
- `tabs_create_mcp` / `tabs_close_mcp` — optional tab management.
- `navigate` — open Amazon and report URLs.
- `javascript_tool` — run targeted in-page extraction evals. Prefer this over
  `get markdown`.
- `browser_batch` — run a predictable sequence (navigate → probe → extract) in **one**
  round-trip. Use it for every per-page fetch; it is ~4× cheaper than separate calls.
- `computer` — screenshots or pointer clicks only if needed to resolve a visible
  browser state after the user has handled login/CAPTCHA.

**Token discipline (this skill is browser-heavy — keep payloads small):**
- Batch with `browser_batch` whenever ≥2 steps are predictable.
- Evals must return **only what's needed** — counts and trimmed text, never raw page
  dumps or URLs (the MCP truncates at ~1 KB and the content filter rejects page text).
- Verify state with DOM **count** probes (e.g. `{reviewNodes, themes}`), not screenshots.
  Take at most **one** screenshot — the finished report — to share with the user.

## Phase 1 — Amazon top 10 (Claude-in-Chrome MCP)

Goal: capture the top ~10 Amazon listings for the keyword. If the Helium 10 Xray
overlay/table is present on the search page, also capture each product's 30-day
units sold and revenue. If Xray is absent, record `null` sales fields and
`salesSource: "none"`; never fabricate sales.

### 1.1 Browser setup

1. `mcp__Claude_in_Chrome__list_connected_browsers`.
2. `mcp__Claude_in_Chrome__select_browser` with the local browser's `deviceId`.
3. `mcp__Claude_in_Chrome__tabs_context_mcp` with `createIfEmpty: true`.
4. Reuse the selected `tabId` through Phase 1.

### 1.2 Navigate to Amazon search

Navigate the tab to:

```text
https://www.amazon.com/s?k=<keyword>&language=en_US
```

Do not apply a price-band filter. Review mining should follow the most relevant
and most-reviewed competitive set.

If the user has Helium 10 and wants sales weighting, ask them to open Xray on
this search results page before extraction. If they do not, continue with null
sales fields.

### 1.3 Extract product data with eval

Run this via `javascript_tool`. It reads Amazon listing cards and, when present,
looks for Helium 10/Xray rows or cells containing the same ASIN and 30-day sales
labels. DOMs vary by extension version, so this extractor is defensive; it still
returns real page data only.

```js
(function(){
  function txt(el){ return (el && el.textContent || '').replace(/\s+/g,' ').trim(); }
  function num(t){
    if (!t) return null;
    const s = String(t).replace(/[$,]/g,'').trim();
    const m = s.match(/([\d.]+)\s*([KMB])?/i);
    if (!m) return null;
    const base = parseFloat(m[1]);
    const mult = !m[2] ? 1 : m[2].toUpperCase()==='K' ? 1e3 : m[2].toUpperCase()==='M' ? 1e6 : 1e9;
    return Math.round(base * mult);
  }
  function money(t){ const n = num(t); return n == null ? null : n; }
  function rating(t){ const m = String(t||'').match(/([\d.]+)\s+out of\s+5/i); return m ? parseFloat(m[1]) : null; }
  function reviews(t){ const s = String(t||'').replace(/[(),]/g,'').trim(); const m = s.match(/([\d.]+)\s*([KMB])?/i); if(!m) return null; const n = parseFloat(m[1]); const x = m[2] ? ({K:1e3,M:1e6,B:1e9})[m[2].toUpperCase()] : 1; return Math.round(n*x); }
  function xrayByAsin(){
    const map = new Map();
    const nodes = [...document.querySelectorAll('[data-asin], tr, [role=row], div')];
    for (const node of nodes) {
      const all = txt(node);
      const asin = (node.getAttribute && node.getAttribute('data-asin')) || ((all.match(/\bB0[A-Z0-9]{8}\b|\b[0-9A-Z]{10}\b/)||[])[0]);
      if (!asin || map.has(asin)) continue;
      if (!/xray|helium|30\s*day|30d|sales|units|revenue/i.test(all)) continue;
      const unitsMatch = all.match(/(?:30\s*day|30d)?\s*(?:units?|sales)\D{0,20}([\d,.]+[KMB]?)/i) || all.match(/([\d,.]+[KMB]?)\s*(?:units?|sales)/i);
      const revMatch = all.match(/(?:30\s*day|30d)?\s*revenue\D{0,20}\$?\s*([\d,.]+[KMB]?)/i) || all.match(/\$\s*([\d,.]+[KMB]?)/);
      const units30d = unitsMatch ? num(unitsMatch[1]) : null;
      const revenue30d = revMatch ? money(revMatch[1]) : null;
      if (units30d != null || revenue30d != null) map.set(asin, { units30d, revenue30d });
    }
    return map;
  }
  const xray = xrayByAsin();
  const seen = new Set();
  const out = [];
  for (const el of document.querySelectorAll('.s-result-item[data-asin]:not([data-asin=""])')) {
    const asin = el.getAttribute('data-asin');
    if (!asin || seen.has(asin)) continue;
    seen.add(asin);
    const title = txt(el.querySelector('h2 span'));
    if (!title) continue;
    const priceEl = el.querySelector('.a-price .a-offscreen');
    const imageEl = el.querySelector('img.s-image');
    const ratingEl = el.querySelector('.a-icon-alt');
    const reviewEl = el.querySelector('a[href*="customerReviews"] span, a[href*="#customerReviews"] span, [data-csa-c-type="link"] .a-size-base');
    const imgId = imageEl ? (imageEl.src.match(/\/images\/I\/([^.]+)\./)||[])[1] || '' : '';  // store the ID, not the full URL — the template rebuilds it
    const sales = xray.get(asin) || {};
    out.push({
      asin,
      title: title.slice(0, 80),               // trim — the report truncates anyway; keeps products.json small
      imageId: imgId,
      amazonUrl: 'https://www.amazon.com/dp/' + asin,
      price: priceEl ? parseFloat(priceEl.textContent.replace(/[^0-9.]/g,'')) : null,
      rating: rating(txt(ratingEl)),
      reviewCount: reviews(txt(reviewEl)),
      units30d: sales.units30d == null ? null : sales.units30d,
      revenue30d: sales.revenue30d == null ? null : sales.revenue30d,
      salesSource: (sales.units30d != null || sales.revenue30d != null) ? 'helium10' : 'none'
    });
    if (out.length >= 10) break;
  }
  return JSON.stringify(out);
})()
```

### 1.4 Xray market fields (Helium 10 — 0 metered actions)

If the Helium 10 **Xray** overlay/table is open on the SERP, capture per ASIN, in
addition to the fields above: `bsr`, `priceXray`, `reviewVelocity` (new reviews in the
last 30 days, if shown), `listingAgeMonths`, `fulfillment` (FBA/FBM/AMZ) — alongside
the existing `units30d`, `revenue30d`, `salesSource:"helium10"`. **The Xray DOM varies
by extension version — before extracting, inspect the open Xray overlay with a DOM
probe and target its real row selectors (each row carries the ASIN plus columns for
Sales, Revenue, BSR, Price, Review Velocity, Age, Fulfillment); map columns by header
text.** Reading the already-open overlay does **not** consume a Helium 10 lookup.
Missing column → `null`. Xray absent → all these are `null` and `salesSource:"none"`.
**Never fabricate values.**

### 1.5 Write products.json

Write the resulting array to `<run-dir>/products.json`. With trimmed titles and an
`imageId` (not a full URL), all 10 records fit in ~2 KB — return the eval result and
write it in **one or two `javascript_tool` calls**, no need to slice it into many
pieces. (`imageId` is the Amazon image id; the report rebuilds the URL as
`https://m.media-amazon.com/images/I/<imageId>._AC_UL640_.jpg`.)

```json
[
  {
    "asin": "B0EXAMPLE",
    "title": "Product title (trimmed to 80 chars)",
    "imageId": "91ihmbCtmlL",
    "amazonUrl": "https://www.amazon.com/dp/B0EXAMPLE",
    "price": 24.99,
    "rating": 4.5,
    "reviewCount": 1234,
    "units30d": null,
    "revenue30d": null,
    "bsr": null,
    "priceXray": null,
    "reviewVelocity": null,
    "listingAgeMonths": null,
    "fulfillment": null,
    "salesSource": "none"
  }
]
```

## Phase 1.6 — Cerebro keyword universe (Helium 10, 1 metered action)

> **Helium 10 usage cap — at most 3 metered actions per run.** Cerebro/Magnet lookups
> consume monthly plan usage and ARE counted; scraping the already-open Xray overlay
> does **not**. Maintain a counter; before a metered action, if the counter is already
> 3, **skip** it and note `H10 usage cap reached`. The flow below spends exactly **1**.
> Record the final count as `h10LookupsUsed` in `reviews.js`.

If Helium 10 is available and the counter is < 3:

1. Pick the top **2–3 ASINs** by `revenue30d` (fallback `reviewCount` when no Xray).
2. In the logged-in Chrome, `navigate` to Cerebro (`https://members.helium10.com/cerebro`),
   enter the 2–3 ASINs as a **multi-ASIN reverse lookup**, set the search-volume filter
   to **≥ 300**, and **run it once** — this is the **1 metered action** (increment the
   counter to 1).
3. Extract the top ~40 keyword rows.

**Validate the live SPA DOM** (the ASIN input, the run/"Get Keywords" trigger, the
results-table rows, pagination) with DOM probes before extracting. Drive it with
`browser_batch` and the token-discipline rules — return counts/trimmed rows, stash +
slice large tables, **never** raw page dumps.

Write `<run-dir>/keywords.json`:

```json
[
  { "phrase": "odor free compost bin", "searchVolume": 2400,
    "ranks": { "B0EXAMPLE1": 38, "B0EXAMPLE2": null }, "cpr": 12 }
]
```

If Cerebro is unreachable, not logged in, or the cap is reached, write `keywords.json`
as `[]` and note the reason; the run continues **review-only** (no demand validation,
no Launch-Keywords section). **Never fabricate search volumes or ranks.**

## Phase 2 — Fetch reviews (Claude-in-Chrome MCP, no fallback)

Goal: fetch the most-helpful critical and positive reviews per ASIN.

For each product in `products.json`, navigate to both polarities:

```text
https://www.amazon.com/product-reviews/<ASIN>/?filterByStar=critical&sortBy=helpful&pageNumber=<N>
https://www.amazon.com/product-reviews/<ASIN>/?filterByStar=positive&sortBy=helpful&pageNumber=<N>
```

**Depth (adaptive — saves ~⅔ of page loads):** fetch **page 1 only** of each polarity
(≈10 reviews) by default. Fetch **page 2 only for high-volume products**
(`reviewCount > 5000`). Helpful-sorted page 1 already saturates the themes.

**Batch each page in one call.** Run navigate → gate-probe → extract for a page inside
a single `browser_batch` (the `navigate` action, then the two `javascript_tool` evals).
That's ~4× fewer round-trips than separate calls.

Review pages require the logged-in Amazon profile. If a login wall, CAPTCHA,
verification interstitial, or unexpected "no reviews" gate appears, stop and ask the
user to resolve it; do not substitute data from another source.

### 2.1 Block/gate probe

Run after navigation and before extraction:

```js
(function(){
  var bt = document.body ? document.body.innerText : '';
  var blocked = /enter the characters you see below|not a robot|automated access|api-services-support/i.test(bt);
  var signin = /^\s*(Amazon Sign-In|Sign-In)\s*$/i.test(document.title || '');
  var reviewNodes = document.querySelectorAll('[data-hook="review"]').length;
  var noReviews = reviewNodes === 0 && /no customer reviews|no reviews/i.test(bt);
  return JSON.stringify({ blocked: blocked || signin, noReviews: noReviews, reviewNodes: reviewNodes });
})()
```

`blocked:true` hard-stops until the user fixes the browser state. A real
`noReviews:true` product stays in `products.json`, contributes zero reviews, and is
excluded from theme mining. **Never return raw page text or the page URL from an eval**
— the MCP content filter rejects evals that echo cookie/query-string/page text, so
return only flags and counts (as above).

### 2.2 Extract reviews with eval

Run this on each review page. It trims bodies to 150 chars and keeps only the **8
most-helpful** reviews — enough for a theme plus a usable quote, at a fraction of the
tokens. It returns review text only from the loaded page.

```js
(function(){
  function txt(el){ return (el && el.textContent || '').replace(/\s+/g,' ').trim(); }
  function stars(t){ const m = String(t||'').match(/([\d.]+)\s+out of\s+5/i); return m ? parseFloat(m[1]) : null; }
  function helpful(t){
    if (!t) return 0;
    if (/one person/i.test(t)) return 1;
    const m = t.replace(/,/g,'').match(/(\d+)/);
    return m ? parseInt(m[1],10) : 0;
  }
  return JSON.stringify([...document.querySelectorAll('[data-hook="review"]')].map(r => ({
    stars: stars(txt(r.querySelector('[data-hook="review-star-rating"], [data-hook="cmps-review-star-rating"]'))),
    title: txt(r.querySelector('[data-hook="review-title"]')).replace(/^\d(?:\.\d)?\s+out of\s+5\s+stars\s*/i,'').slice(0,90),
    body: txt(r.querySelector('[data-hook="review-body"]')).slice(0,150),
    verified: !!r.querySelector('[data-hook="avp-badge"]'),
    helpfulVotes: helpful(txt(r.querySelector('[data-hook="helpful-vote-statement"]')))
  })).filter(x => x.body)
    .sort((a,b) => b.helpfulVotes - a.helpfulVotes)
    .slice(0,8));
})()
```

If the trimmed result still exceeds the tool-output limit, stash it
(`window.__R = […]`) and read it back as one condensed string in 1–2 slices, rather
than returning many separate fields.

If you fetched a 2nd page (high-volume product), merge it and de-duplicate within each
ASIN/polarity by `stars + title + body`, then keep the ~8–16 most-helpful per polarity.
Preserve Amazon's helpful order.

### 2.3 Write reviews-raw.json

```json
{
  "B0EXAMPLE": {
    "critical": [
      {
        "stars": 2,
        "title": "Stopped working",
        "body": "Worked for two weeks and then failed.",
        "verified": true,
        "helpfulVotes": 14
      }
    ],
    "positive": [
      {
        "stars": 5,
        "title": "Useful every day",
        "body": "Simple, sturdy, and exactly as described.",
        "verified": true,
        "helpfulVotes": 8
      }
    ]
  }
}
```

## Phase 3 — Map-reduce review analysis

Goal: turn raw reviews into category-level complaint and praise themes, with
real quotes and product attribution. This phase is agent analysis; there is no
Node helper.

### 3.1 Preconditions

- `<run-dir>/products.json` exists.
- `<run-dir>/reviews-raw.json` exists.
- At least one product has fetchable critical or positive reviews. Products with
  zero reviews remain in the product strip but do not contribute themes.

### 3.2 Map: per-product themes

For each ASIN independently, read its raw critical and positive reviews and
extract:
- Top complaint themes from `critical` reviews.
- Top praise themes from `positive` reviews.
- Short theme labels.
- One-line descriptions.
- `count`, the number of reviews for that ASIN/polarity that support the theme.
- One or two representative verbatim quotes, preferring verified reviews and
  higher `helpfulVotes`.

Grounding is strict: every theme must be supported by reviews in
`reviews-raw.json`; every quote must be copied verbatim from a real review body
and trimmed only for length.

Write `<run-dir>/reviews-map.json`:

```json
{
  "B0EXAMPLE": {
    "complaints": [
      {
        "theme": "Durability / early failure",
        "description": "Buyers report the product breaking or failing soon after purchase.",
        "count": 5,
        "quotes": [
          { "quote": "Worked for two weeks and then failed.", "stars": 2 }
        ]
      }
    ],
    "praises": [
      {
        "theme": "Easy daily use",
        "description": "Buyers like that it is simple to set up and use repeatedly.",
        "count": 7,
        "quotes": [
          { "quote": "Simple, sturdy, and exactly as described.", "stars": 5 }
        ]
      }
    ]
  }
}
```

### 3.3 Reduce: category themes

Merge per-product themes when they describe the same underlying issue or benefit,
for example "stitching frays" and "seams fall apart" become
"Durability / stitching".

For each merged complaint theme compute:
- `mentions`: sum of per-product counts.
- `productCount`: number of products where the theme appears.
- `affectedAsins`: ASINs where the theme appears.
- `severity`: `1` cosmetic, `2` functional/returns, `3` safety, trust, or
  severe failure.
- `exampleQuotes`: the best 2-3 verbatim quotes, each with `asin` and `stars`.

For each merged praise theme compute the same fields except `severity`.

Sales weighting: if any product has `salesSource: "helium10"`, compute
`affectedUnits30d` as the sum of non-null `units30d` across `affectedAsins`, then
rank themes by:

```text
mentions * (1 + log10(1 + affectedUnits30d))
```

If every product has `salesSource: "none"`, rank by `mentions`, then
`productCount`, then quote helpfulness/context quality. Treat null units as `0`.
The rank score is for ordering only; it does not need to be written to
`reviews.js`.

### 3.4 Opportunity brief

Write:
- `mustFix`: top 3-5 complaint themes reframed as build or sourcing requirements.
- `mustKeep`: top 3-5 praise themes that a competitive product must preserve.
- `angle`: a 1-2 sentence differentiation thesis grounded in the gap between
  common complaints and common praises.

Do not invent market claims. The brief must be traceable to `reviews-raw.json`
quotes and the reduced themes.

### 3.5 Keyword match, market sizing & verdict (Helium 10, 0 metered)

If `keywords.json` and/or Xray data are present (pure analysis — no lookups):

- **Theme ↔ keyword match.** For each top must-fix/must-keep theme, find the best
  semantically-matching keyword in `keywords.json` and attach `keyword`, `searchVolume`,
  `demandValidated: true`. Only attach a keyword that genuinely expresses the theme;
  otherwise leave `demandValidated: false` and omit `keyword`.
- **Launch keywords / gaps.** Build `keywords.gaps` = high-`searchVolume` phrases the
  covered competitors rank poorly for (or none target). Build
  `opportunity.validatedDifferentiators` = the must-fix themes that ARE demand-validated,
  each with its keyword + volume.
- **Market sizing.** `market` = { `totalRevenue30d`, `totalUnits30d` (sum over Xray
  products), `priceLow`/`priceHigh` (from the strip), `weakCompetitorCount` (top sellers
  with `rating < 4.3` OR `reviewCount < 200`), `note` }.
- **Verdict.** `verdict` = { `call`: `"GO" | "WATCH" | "SKIP"`, `reasons`: [2–3] }
  weighing (a) demand size, (b) competition / room (fragmented vs brand-dominated,
  review barrier), and (c) whether a demand-validated differentiator gap exists.
  **Reasons must trace to real data.** If `market` or `keywords` is missing, still
  render a verdict but state what could not be assessed (e.g. "demand not validated —
  Cerebro unavailable").

When Helium 10 data is absent, set `market` and `keywords` to `null`, omit the
per-theme keyword fields, and the report renders exactly as the review-only version.

### 3.6 Write reviews.js

Write `<run-dir>/reviews.js` exactly as a global data file:

```js
window.__REVIEW_DATA__ = {
  keyword: "example keyword",
  date: "2026-06-21",
  products: [
    {
      asin: "B0EXAMPLE",
      title: "Product title",
      imageId: "91ihmbCtmlL",
      amazonUrl: "https://www.amazon.com/dp/B0EXAMPLE",
      price: 24.99,
      rating: 4.5,
      reviewCount: 1234,
      units30d: null,
      revenue30d: null,
      bsr: null,             // Helium 10 Xray (nullable)
      reviewVelocity: null,  // new reviews in last 30d (nullable)
      fulfillment: null,     // "FBA" | "FBM" | "AMZ" | null
      salesSource: "none"
    }
  ],
  totals: {
    reviewsAnalyzed: 40,
    critical: 20,
    positive: 20,
    productsCovered: 1
  },
  complaintThemes: [
    {
      theme: "Durability / early failure",
      description: "Buyers report the product breaking or failing soon after purchase.",
      keyword: "heavy duty <product>", searchVolume: 1900, demandValidated: true,  // Helium 10 (optional, only when a real keyword matched)
      mentions: 5,
      productCount: 1,
      affectedAsins: ["B0EXAMPLE"],
      severity: 2,
      exampleQuotes: [
        { quote: "Worked for two weeks and then failed.", asin: "B0EXAMPLE", stars: 2 }
      ]
    }
  ],
  praiseThemes: [
    {
      theme: "Easy daily use",
      description: "Buyers like that it is simple to set up and use repeatedly.",
      mentions: 7,
      productCount: 1,
      affectedAsins: ["B0EXAMPLE"],
      exampleQuotes: [
        { quote: "Simple, sturdy, and exactly as described.", asin: "B0EXAMPLE", stars: 5 }
      ]
    }
  ],
  opportunity: {
    mustFix: ["Improve durability and validate with longer-cycle QA."],
    mustKeep: ["Keep setup simple and instructions clear."],
    angle: "Win by pairing the category's easy-use promise with visibly sturdier materials and clearer durability proof.",
    validatedDifferentiators: [
      { theme: "Durability / early failure", keyword: "heavy duty <product>", searchVolume: 1900 }
    ]
  },

  // ── Helium 10 layer (all null/omitted when Helium 10 is unavailable) ──
  market: {
    totalRevenue30d: 412000, totalUnits30d: 12800,
    priceLow: 18.99, priceHigh: 53.99,
    weakCompetitorCount: 4, note: "Top 3 listings hold ~58% of revenue; the rest is fragmented."
  },
  keywords: {
    top:  [ { phrase: "main keyword", searchVolume: 18100, ranks: { "B0EXAMPLE": 3 } } ],
    gaps: [ { phrase: "odor free <product>", searchVolume: 2400, why: "top sellers rank past page 1", ranks: { "B0EXAMPLE": 38 } } ]
  },
  verdict: {
    call: "GO",
    reasons: [
      "Sizeable 30-day demand with no single brand dominating.",
      "The #1 complaint maps to a real, searched keyword.",
      "Several top sellers are weak — room to enter."
    ]
  },
  h10LookupsUsed: 1
};
```

## Phase 4 — Open report

Fetch the report renderer from the skill repo on first run only. Save it as
`<run-dir>/report.html`; do not regenerate HTML with the agent.

The report renders top-down: **Verdict banner** (GO/WATCH/SKIP) → **Market panel**
(30d revenue/units, price spread, weak-competitor count) → **Opportunity Brief** →
themes (with keyword chips) → **Launch Keywords** table → product strip (with BSR /
review-velocity tags) → footer (adds `Data sources` + `H10 lookups used: N/3`). Every
Helium 10 block hides automatically when its data is `null`, leaving the review-only
report.

```bash
[ -f "<run-dir>/report.html" ] || curl -fsSL \
  https://raw.githubusercontent.com/AronLEEdev/product-review-analyze-skill/main/report-template.html \
  -o "<run-dir>/report.html"
python3 -m http.server 7860 --directory "<run-dir>" &
```

Then navigate Chrome through the MCP to:

```text
http://localhost:7860/report.html
```

Use a fresh port if a prior server may be caching an old `reviews.js`. The
template loads `reviews.js` via a `<script>` tag; `file://` cannot reliably load
that local sub-resource, so the run directory must be served over http.

**Verify cheaply.** Confirm the render with a single DOM-count probe, not a series of
screenshots:

```js
JSON.stringify({
  products: document.querySelectorAll('.product-card').length,
  complaints: document.querySelectorAll('.theme-card.red').length,
  praises: document.querySelectorAll('.theme-card.green').length,
  brief: !!document.querySelector('.brief')
})
```

Take **one** screenshot of the finished report to share with the user — no more.

## Phase 5 — Combined product dossier (optional, terminal)

The review skill is the **last** of the three-skill FBA pipeline (discovery →
cost → review), so it also assembles the **one-page dossier** that stitches all
three phases together — so the user reads a single report instead of hunting
across three. It **reuses the three skills' data files verbatim; nothing is
recomputed** (zero LLM tokens — the fused verdict is computed client-side by the
template). Run this only when a sibling **cost** run exists for the same product.

**Inputs it looks for** (all produced by the pipeline; each is optional except
this run's `reviews.js`):
- `reviews.js` — this run (`window.__REVIEW_DATA__`). Required.
- `<keyword>/results.js` — the cost run (`window.__FBA_DATA__`), from
  `product-cost-analyze-for-fba`. The review run dir is conventionally
  `<keyword>-reviews/`, so the cost run is the sibling `<keyword>/`.
- `opportunities.js` — a discovery run (`window.__DISCOVERY_DATA__`) from
  `product-opportunity-finder`, if one exists. The dossier renders cost+review
  only when it's absent.

### 5.1 Assemble the dossier directory

```bash
DOSSIER="<review-run>/dossier"
mkdir -p "$DOSSIER"
cp "<review-run>/reviews.js" "$DOSSIER/reviews.js"
[ -f "<cost-run>/results.js" ] && cp "<cost-run>/results.js" "$DOSSIER/results.js"
```

### 5.2 Discovery slice (optional)

If a discovery `opportunities.js` is available, extract the **one** niche row for
this product and write it as `window.__DISCOVERY_ITEM__` (the single niche object
+ the run's `category`/`date`). Match by `nextSteps.reviewSkillKeyword` (fallback:
fuzzy match on `niche`). Skip this file entirely if no discovery data exists.

```bash
node -e '
const fs=require("fs");
const opp=process.argv[1], kw=process.argv[2], out=process.argv[3];
const d=JSON.parse(fs.readFileSync(opp,"utf8").replace(/^window.__DISCOVERY_DATA__ = /,"").replace(/;\s*$/,""));
const all=[...(d.shortlist||[]),...(d.runnersUp||[])];
const n=all.find(x=>((x.nextSteps||{}).reviewSkillKeyword||"").toLowerCase()===kw.toLowerCase())
       ||all.find(x=>(x.niche||"").toLowerCase().includes(kw.toLowerCase()));
if(!n){ console.error("no matching niche; skipping discovery.js"); process.exit(0); }
fs.writeFileSync(out,"window.__DISCOVERY_ITEM__ = "+JSON.stringify(Object.assign({category:d.category,date:d.date},n),null,2)+";");
console.log("wrote discovery.js for:",n.niche);
' "<opportunities.js path>" "<keyword>" "$DOSSIER/discovery.js"
```

### 5.3 Fetch the template, serve, open

The renderer is fetched from this skill's repo on first run (like `report.html`).
It loads `discovery.js` · `results.js` · `reviews.js` via `<script>` tags and
must be served over http (a `file://` URL can't load the sub-resources).

```bash
[ -f "$DOSSIER/dossier.html" ] || curl -fsSL \
  https://raw.githubusercontent.com/AronLEEdev/product-review-analyze-skill/main/dossier.html \
  -o "$DOSSIER/dossier.html"
python3 -m http.server 7870 --directory "$DOSSIER" &
```

Then `navigate` to `http://localhost:7870/dossier.html`. The template computes a
**fused verdict** — `BUILD` (review GO + discovery score ≥ 70 + best net margin ≥
20%), `TEST` (WATCH, or attractive-but-caveated), or `PASS` (review SKIP or best
margin < 10%) — then renders a snapshot row and three stacked sections
(Discovery · Cost · Review). Any missing data file degrades gracefully. It is
**null-safe**: values are filtered with `num()` before formatting, so nullable
metrics render `—`, never a phantom `$0` (see the `Number(null)===0` trap).

Verify with one DOM-count probe, then take **one** screenshot to share:

```js
JSON.stringify({ verdict:(document.querySelector('.call')||{}).textContent,
  tiles:document.querySelectorAll('.tile').length,
  sections:document.querySelectorAll('section').length })
```

## Error handling (no fallback)

- Login wall, CAPTCHA, verification slider, or bot-check in Phase 1 or Phase 2:
  stop, ask the user to resolve it, then continue.
- A product with zero fetchable reviews: keep it in `products.json` and the
  report product strip, exclude it from theme mining, and decrement
  `productsCovered`.
- Helium 10 absent: write `units30d: null`, `revenue30d: null`,
  `salesSource: "none"` and rank by mentions/product count.
- Phase 3 must cite only real quotes from `reviews-raw.json`. If a polarity has
  no reviews for a product, that product contributes nothing to that side.
- Never fabricate reviews, sales, revenue, themes, quotes, ASINs, or Amazon page
  states.
