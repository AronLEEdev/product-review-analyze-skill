# product-review-analyze-skill

A Claude skill for Amazon review mining. Given a product keyword, it drives the
user's logged-in Chrome through the Claude-in-Chrome MCP, collects the top Amazon
listings and their critical/positive reviews, clusters category-level complaints
and praises, and renders a static HTML opportunity report.

It is the review-mining companion to `product-cost-analyze-for-fba` and follows
the same packaging pattern: install the single `SKILL.md`, fetch the report
template from this repo at run time, write a `window.__REVIEW_DATA__` data file,
and serve the report over http.

**Helium 10 layer (optional).** With a Helium 10 subscription, the skill fuses
**Xray** market data (30-day revenue/units, BSR, review velocity, price spread) and
one **Cerebro** keyword lookup into a **GO / WATCH / SKIP product-opportunity brief** —
sizing the market, validating each review theme against real search volume, and
surfacing launch keywords. Metered Helium 10 lookups are **capped at 3 per run**
(default 1). Without Helium 10, the skill degrades to the review-only report.

## Pipeline

1. **Phase 1: Amazon top 10** — use Claude-in-Chrome MCP to open Amazon search
   for the keyword and extract ASIN, title, price, rating, review count, image,
   URL, and optional Helium 10 Xray 30-day units/revenue.
2. **Phase 2: Review fetch** — visit each ASIN's Amazon review pages for
   critical and positive reviews, sorted by helpful, about two pages per
   polarity.
3. **Phase 3: Map-reduce analysis** — extract per-product themes, merge them
   into category complaints and praises, sales-weight rank when Helium 10 data is
   present, and write `reviews.js`.
4. **Phase 4: Report** — fetch `report-template.html` as `report.html`, serve
   the run directory over http, and load the static report in Chrome.

## Preconditions

| Requirement | Needed for | Required? |
|---|---|---|
| Chrome + **Claude-in-Chrome MCP** extension, connected | the whole workflow | **Required** |
| **Amazon account, logged in** (same Chrome profile) | review pages are gated behind login | **Required** |
| **Python 3** (or any static server) | serve the report over http in Phase 4 | **Required** |
| **Helium 10** extension + account | Phase 1 30-day units sold + revenue, else null | Optional |

No automated login or CAPTCHA solving. If Amazon blocks access or asks for
verification, the workflow stops and waits for the user to resolve it in Chrome.

## Install

Copy or install `SKILL.md` as a Claude/Codex skill. The end user only needs that
one file. During Phase 4, the skill fetches this repo's `report-template.html`
from `main` and saves it into the run directory as `report.html`.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | End-user skill instructions and exact data shapes |
| `report-template.html` | Self-contained static renderer for `reviews.js` |
| `sample/reviews.sample.js` | Small fixture for template render checks |
| `LICENSE` | Project license |

Typical run output lives outside the repo at
`~/Documents/product-research/<keyword>-reviews/` and includes `products.json`,
`reviews-raw.json`, `reviews-map.json`, `reviews.js`, and `report.html`.
