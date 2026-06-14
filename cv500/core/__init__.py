"""Shared core for the cv500 toolkit.

Modules:
  provenance  -- source-URL + retrieval-timestamp stamping
  needsdata   -- NEEDS-DATA / MISSING result helpers and the per-item result type
  fiscal      -- Indian fiscal-year + quarter normalisation
  naming      -- company-name cleaning; file + zip naming
  manifest    -- manifest CSV writer including the MISSING section
  crawl       -- polite fetcher (robots.txt, UA, rate-limit, retries, Playwright fallback)
  pdfval      -- PDF validation (is-this-an-AR / is-this-a-transcript) + stated-period extraction
"""
