"""cv500 — operator-side data-collection toolkit for Indian listed equities.

This package exposes discrete CLI subcommands that share a common ``core``. It is
explicitly NOT a monolithic end-to-end pipeline: each subcommand runs, tests, and
fails independently.

The tools collect, validate, organise, and report. They never make investment
decisions, never assign a final verdict on a company, never transact, and never
fabricate data. When something cannot be found, the tools say so (NEEDS-DATA /
MISSING) and name exactly what is missing.

Target sources are INDIAN ONLY (company IR sites, BSE, NSE, screener.in, the four
rating agencies, SEBI, MCA). The toolkit never fetches SEC / EDGAR or any US source.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
