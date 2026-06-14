"""triage-pack — the light fetch sufficient to run the cheap P0/P1 kill gates
(Section 6.2).

This is NOT the full evidence pull. It fetches only:
  * the screener export (if supplied / locatable),
  * a P0 surveillance pass (same checks as p0-check),
  * the LATEST SINGLE annual report (for auditor opinion, contingents note, cash-flow
    statement).

It deliberately does not pull the 5-AR + transcript set — that is `fetch-filings`,
reserved for names that survive P1. Output: a small folder + a summary listing what is
present for P0/P1 and what is MISSING (naming each gap).
"""

from __future__ import annotations

import os
import shutil
from typing import List, Optional

from .. import specs
from ..core import naming, pdfval
from ..core.crawl import Crawler
from ..core.needsdata import Result, passed, needs_data, flag
from ..core.report import print_results, write_results_csv
from . import fetch_filings as ff

_RULE = "Section 6.2 (triage-pack: light fetch for P0/P1 gates)"

# P1 data needs and where each is normally sourced (Section 5.2).
_P1_NEEDS = [
    ("promoter pledge", "shareholding pattern / screener"),
    ("promoter holding %", "shareholding pattern / screener"),
    ("reported PAT (latest FY)", "screener / annual report"),
    ("D/E ratio", "screener / annual report"),
    ("3-yr cumulative OCF and OCF/PAT", "annual report cash-flow statements"),
    ("auditor opinion", "latest annual report (auditor's report)"),
    ("contingent liabilities + commitments vs net worth", "latest annual report (notes)"),
    ("equity dilution over 3 yrs", "annual report / shareholding history"),
]


def _fetch_latest_ar(crawler: Crawler, url: str, name: str, folder: str
                     ) -> Optional[Result]:
    """Discover candidates, pick the latest AR, download+validate, save the PDF.
    Returns a Result (PASS with provenance, or NEEDS-DATA)."""
    cands = ff.discover_candidates(crawler, url)
    for c in cands:
        ff.classify(c)
    ars = [c for c in cands if c.doc_type == "AR" and c.fiscal_year]
    if not ars:
        return needs_data("latest annual report",
                          "no dated annual-report PDF found on the company site "
                          "(needed for auditor opinion / contingents / cash-flow)",
                          rule=_RULE)
    anchor = max(c.fiscal_year for c in ars)
    best = sorted([c for c in ars if c.fiscal_year == anchor],
                  key=ff._ar_score, reverse=True)
    for c in best[:ff.MAX_DOWNLOAD_ATTEMPTS_PER_SLOT]:
        res = crawler.fetch(c.url, want_binary=True, source_site=c.source_site)
        if not res.ok or not res.content:
            continue
        v = pdfval.validate(res.content, expected_kind=pdfval.KIND_AR,
                            expected_fiscal_year=anchor)
        if not v.is_pdf or (v.kind != pdfval.KIND_UNKNOWN and v.kind != pdfval.KIND_AR):
            continue
        fname = naming.ar_filename(name, anchor)
        path = os.path.join(folder, fname)
        with open(path, "wb") as fh:
            fh.write(res.content)
        return passed("latest annual report",
                      f"{fname} saved ({v.status})", rule=_RULE, provenance=res.provenance)
    return needs_data("latest annual report",
                      "annual-report candidate(s) found but none downloaded/validated",
                      rule=_RULE)


def run(args) -> int:
    ident = args.ticker or args.name or "COMPANY"
    name = naming.clean_company_name(args.name or args.ticker or "COMPANY")
    out_dir = os.path.abspath(args.out)
    folder = os.path.join(out_dir, f"triage_{name}")
    os.makedirs(folder, exist_ok=True)
    results: List[Result] = []

    print(f"== triage-pack ==  {ident}  ->  {folder}")

    # 1) screener export
    if args.screener_csv and os.path.exists(args.screener_csv):
        dest = os.path.join(folder, os.path.basename(args.screener_csv))
        try:
            shutil.copy2(args.screener_csv, dest)
            results.append(passed("screener export", f"present -> {os.path.basename(dest)}",
                                  rule=_RULE))
        except OSError as e:
            results.append(flag("screener export", f"could not copy: {e}", rule=_RULE))
    else:
        results.append(needs_data("screener export",
                                  "not supplied/locatable (--screener-csv) — P1 numeric "
                                  "gates (pledge, holding, PAT, D/E) read from it", rule=_RULE))

    # 2) P0 surveillance pass — point at p0-check rather than re-fetching the blocking
    # surveillance sources here (p0-check stamps each source URL itself).
    crawler = Crawler(verbose=False, timeout=10, max_retries=0)
    if not (args.ticker or args.name):
        results.append(needs_data("P0 surveillance", "supply --ticker/--name to run P0",
                                  rule=_RULE))
    else:
        results.append(needs_data(
            "P0 surveillance",
            f"P0 checks require confirmation at their sources "
            f"(GSM/ASM/INC/SEBI-SFIO-ED/delisting). Run `cv500 p0-check --ticker {ident}` "
            f"for the stamped source URLs.", rule=_RULE))

    # 3) latest single annual report
    if args.url:
        ar_res = _fetch_latest_ar(crawler, args.url, name, folder)
        if ar_res:
            results.append(ar_res)
    else:
        results.append(needs_data("latest annual report",
                                  "no --url supplied to locate the latest AR", rule=_RULE))

    # 4) P1 readiness map
    have_screener = any(r.name == "screener export" and r.status == "PASS" for r in results)
    have_ar = any(r.name == "latest annual report" and r.status == "PASS" for r in results)
    for need, src in _P1_NEEDS:
        if "screener" in src and have_screener:
            results.append(passed(f"P1 input: {need}", f"obtainable from {src}", rule=_RULE))
        elif "annual report" in src and have_ar:
            results.append(passed(f"P1 input: {need}", f"obtainable from {src} (manual read)",
                                  rule=_RULE))
        else:
            results.append(needs_data(f"P1 input: {need}",
                                      f"source not present yet ({src})", rule=_RULE))

    print_results("triage-pack", results)
    write_results_csv(os.path.join(folder, "triage_summary.csv"), results)
    print(f"\n  triage folder: {folder}")
    print("  (this is the light P0/P1 pack — run fetch-filings only for names that survive P1)")
    return 0
