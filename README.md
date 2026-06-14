# cv500 — data-collection toolkit for Indian listed equities

`cv500` is an **operator-side, command-line toolkit** for gathering public filings and
market data on **Indian listed equities** into a local research vault. A human runs
these tools; a *separate* AI agent later reasons only over what the tools collected.

That boundary is the whole design:

- The tools **collect, validate, organise, and report.** They **never** make investment
  decisions, never assign a final verdict on a company, never transact, and **never
  fabricate data.**
- When a document or number cannot be found or fetched, the tools say so plainly —
  **NEEDS-DATA** (for data commands) or a **MISSING** list (for fetch commands),
  **naming exactly what is missing.** A short, honest result beats a padded one.
- Sources are **Indian only** (company IR sites, BSE, NSE, screener.in, the four rating
  agencies, SEBI, MCA). The toolkit **never** fetches SEC / EDGAR or any US source —
  this is enforced in code (`core/crawl.py`).

It is **not** one monolithic pipeline. Each subcommand runs, tests, and fails
**independently**, because they hit different sources with different reliability.

---

## Install

Requires Python 3.9+.

```bash
# from the repository root (the folder containing pyproject.toml)
python -m pip install -e .
```

This installs the `cv500` CLI and four light runtime dependencies: `requests`,
`beautifulsoup4`, `lxml`, `pypdf`. (Numerics — percentiles, the reverse-DCF solver —
are pure-Python; no numpy/scipy/pandas.)

### Optional: JavaScript-rendered IR pages (Playwright)

Most sites work with static fetching. For a few JavaScript-heavy IR pages, `fetch-filings`
can fall back to a headless browser **if Playwright is installed** — otherwise it simply
degrades to the MISSING list (it never crashes for lack of it):

```bash
python -m pip install playwright
playwright install chromium
```

### Run the tests

```bash
python -m pip install pytest
python -m pytest -q
```

---

## Commands

Run `cv500 -h` for the list, or `cv500 <command> -h` for a command's options. Every
command writes only to its output directory (default `./outputs`).

### `fetch-filings` — annual reports + concall transcripts (Phase 1 priority)

Given a company website, find and download the latest **N fiscal years** (default 5) of
annual reports plus the earnings-call transcripts for those same years, validated and
packaged into one zip named after the company.

```bash
cv500 fetch-filings --url https://www.pidilite.com --ticker PIDILITIND --years 5 --out ./outputs/pidilite
```

- Infers "latest N years" from what **actually exists** on the site (anchors on the most
  recent annual report found — it does not demand the current calendar year).
- Normalises Indian FY/quarter notations (`FY24`, `2023-24`, `Q1FY25`, `Apr-Jun 2024`, …).
- **Validates every PDF** before keeping it: confirms it is the right document type
  (annual report vs transcript) and cross-checks the document's own stated fiscal year /
  quarter against the link, preferring the document's stated period. Files that are the
  wrong kind, the wrong year, or unconfirmable junk (e.g. a regulatory intimation, an
  audio-recording notice) are rejected.
- Output: `{NAME}_5yr_AR_EC-Transcripts.zip` with `Annual_Reports/`,
  `Earnings_Call_Transcripts/`, and a `_manifest.csv`. The manifest ends with a
  **MISSING** section naming every grid cell (year × {AR, Q1–Q4}) that could not be
  found, with the reason (`not found` / `blocked` / `site error`).
- `--ticker` enables a screener.in fallback to fill gaps.

### `p2-5` — locked reverse-DCF triage (Rule 3.3) · pure computation

Solves the 10-year revenue CAGR implied by today's price, then applies the triage stop.
Constants are **locked** (`WACC=14%`, terminal `g=4%`, `tax=25.2%`) and never chosen.

```bash
cv500 p2-5 --ev 1116.49 --revenue 1000 --ebit-margin-series "14,15,15,16,15" \
           --roic-norm 20 --conservative-cagr 12
```

- Verdict: **already priced** (implied g ≥ C) / **pessimism priced** (g ≤ 0.60·C) /
  **inconclusive — operator judgment** (in between; never auto-decided).
- Margins / ROIC / CAGR accept either fractions (`0.15`) or percents (`15`).
- Any missing input → NEEDS-DATA naming it. (`--revenue` is required because the DCF
  must scale FCFF to an absolute EV — see the note in `commands/p2_5.py`.)

### `regime` — FROTHY / NORMAL / CHEAP (Rule 7.3)

```bash
cv500 regime --pe-pctile 84 --pb-pctile 81           # direct percentiles
cv500 regime --series-csv smallcap250_10yr.csv       # CSV with columns: date, pe, pb
```

FROTHY if **both** percentiles ≥ 80; CHEAP if **both** ≤ 25; else NORMAL (including when
the two gauges disagree). Missing either percentile → NEEDS-DATA.

### `liquidity` — stressed exit budget (Rule 7.4)

```bash
cv500 liquidity --ticker RELAXO --delivered-csv delivered.csv --position-value 1500000
```

`budget = 10 trading days × 20% participation × P25(daily delivered value, ~2 yr)`.
CSV columns: `date, delivered_value`. Reports the budget and whether the position fits.
Missing the data (hence P25) → NEEDS-DATA.

### `screen-ingest` — screen-day dedup + memory cross-reference · file-driven

```bash
cv500 screen-ingest --lane-csv CV500-A.csv --lane-csv CV500-B.csv \
                    --graveyard graveyard_log.csv --park-list park_list.csv
```

Dedups across lane exports (key: ISIN → ticker → cleaned name), flags **dual-lane** hits,
and tags each name: `new`, `parked-trigger-fired`, `parked-trigger-not-met`,
`parked-trigger-check-needs-data`, `graveyarded-structural`, `graveyarded-revisitable`.
Writes a tagged hit list CSV. Does **not** re-run any screen.

### `vault-audit` — Tier-1 evidence-floor check · read-only

```bash
cv500 vault-audit --folder path/to/<name>/00_data
```

Checks present vs missing against the floor (≥ 5 annual reports, 8–12 transcripts, ≥ 2
rating rationales, 24 months of exchange filings, shareholding across 8 quarters, peer
presentations). **Never writes** into the inspected folder.

### `p0-check` — P0 surveillance/governance kills

```bash
cv500 p0-check --ticker RELAXO
```

Runs the P0 checks (GSM, ASM, rating INC/withdrawn, SEBI/SFIO/ED, delisting/open-offer),
each against its Indian source with real provenance. Any unreachable/unparseable source →
**NEEDS-DATA** for that check — never an assumed-clean PASS.

### `triage-pack` — light P0/P1 pack

```bash
cv500 triage-pack --ticker RELAXO --url https://www.relaxofootwear.com --screener-csv relaxo.csv
```

Assembles only what the cheap kill gates need: the screener export (if supplied), a P0
pass, and the **latest single** annual report. Produces a P0/P1 readiness map. Does not
pull the full 5-AR + transcript set — that is `fetch-filings`, for names that survive P1.

### `monthly-scan` — Part 08 monitoring sweep

```bash
cv500 monthly-scan --tickers RELAXO,PIDILITIND --price-dir ./prices
```

Per held name: pledge/insider, ASM/GSM, rating actions, MCA charges, bulk/block deals,
the **price-volume anomaly** (−20% in 10 sessions on ≥ 1.5× average delivery → forced
investigation), and news/peer calendar. The price-volume anomaly is computed
deterministically from `--price-dir/<ticker>.csv` (columns `date, close,
delivered_qty|delivered_value`); live filings/news items return NEEDS-DATA naming the
source.

---

## How thresholds are sourced

Every hardcoded number lives in **`cv500/specs.py`**, each annotated with the Part/Rule it
traces to (P0/P1/P1-F kills, the regime gauge, stressed liquidity, the locked reverse-DCF
constants, the evidence floor). Nothing elsewhere invents, rounds, or "interprets" a
threshold; if a value a command needs is not in `specs.py` and not supplied by the user,
the command returns NEEDS-DATA.

---

## Known limitations

This is honest about what is solid and what still needs source-specific iteration.

**Fully working now (deterministic, offline or single-source):**
- `p2-5`, `regime`, `liquidity` — pure computation over supplied inputs/CSVs.
- `screen-ingest`, `vault-audit` — file-driven.
- `fetch-filings` — works cleanly on company IR sites that expose annual-report and
  transcript **PDFs** in static HTML (verified on real Indian sites). PDF validation and
  the MISSING report are reliable.

**Depends on source-specific scraping that may need iteration:**
- **`fetch-filings` across arbitrary site structures.** Crawler robustness across *every*
  IR layout is explicitly out of scope for now. JavaScript-rendered IR pages need
  Playwright; without it those pages degrade to MISSING. Some sites (e.g. ones that proxy
  reports through BSE) will return `blocked` because BSE/NSE reject automated clients.
- **`p0-check` / `triage-pack` P0 / `monthly-scan` live items.** NSE/BSE surveillance,
  SEBI orders, the rating agencies, and MCA either block automated clients or publish via
  dynamic tables/CSVs/APIs that are not authoritatively parsed yet. These commands attempt
  each source politely, stamp real provenance, and return **NEEDS-DATA** naming what a
  human must verify and where — they never assume "clean". Wiring/parsing each endpoint is
  the expected next iteration.
- **`liquidity` / `regime` live pulls.** Currently CSV-driven (NSE delivered-value and the
  Smallcap-250 series are operator-supplied). Live pulls are deferred.

**Politeness & safety (always on):** respects `robots.txt`, descriptive User-Agent,
~1–2 req/sec per host, timeouts + bounded retries with backoff; does not bypass
CAPTCHAs / bot-detection / login walls; never fetches US sources.
