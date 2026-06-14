"""vault-audit — read-only Tier-1 evidence-floor check (Section 6.9).

Checks a name's 00_data/ folder against the Tier-1 evidence floor and reports present
vs missing per category. NEVER writes anything — it only inspects the folder.

Tier-1 floor (specs.VAULT_TIER1_FLOOR):
  >= 5 annual reports
  8-12 concall transcripts
  >= 2 rating rationales
  24 months of exchange filings
  shareholding pattern across 8 quarters
  peer investor presentations
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple

from .. import specs
from ..core.fiscal import parse_fiscal_year, parse_quarter
from ..core.needsdata import Result, passed, needs_data, flag
from ..core.report import print_results, write_results_csv

_RULE = "Section 6.9 (Tier-1 evidence floor)"

# Filename signals per category. A file is counted toward a category if its name (or
# the relative path under the folder) matches that category's pattern.
# Patterns are matched (case-insensitively) against the lowercased relative path.
# NOTE: do NOT rely on \b next to underscores — '_' is a word char, so '\bar' will NOT
# fire after an underscore. We anchor tokens on start-of-string or a separator instead.
_SEP = r"(?:^|[\s_/\\-])"
_CATEGORY_PATTERNS: Dict[str, List[str]] = {
    "annual_reports": [r"annual[\s_-]*report", r"integrated[\s_-]*(?:annual[\s_-]*)?report",
                       _SEP + r"ar[\s_-]*fy\s*\d", _SEP + r"ar[\s_-]*20\d\d"],
    "concall_transcripts": [r"transcript", r"concall", r"con[\s_-]*call", r"earnings[\s_-]*call"],
    "rating_rationales": [r"rating", r"rationale", r"crisil", r"icra", _SEP + r"care",
                          r"india[\s_-]*ratings"],
    "exchange_filings": [r"filing", r"announcement", r"intimation", r"disclosure",
                         _SEP + r"bse", _SEP + r"nse", r"reg[\s_-]*30"],
    "shareholding": [r"shareholding", _SEP + r"shp" + r"(?:$|[\s_/\\-])", r"share[\s_-]*holding"],
    "peer_presentations": [r"peer", r"investor[\s_-]*presentation", r"presentation",
                           _SEP + r"ppt" + r"(?:$|[\s_/\\-])"],
}


def _walk_files(folder: str) -> List[str]:
    out: List[str] = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), folder)
            out.append(rel)
    return out


def _matches(name: str, patterns: List[str]) -> bool:
    low = name.lower()
    return any(re.search(p, low) for p in patterns)


def run(args) -> int:
    folder = os.path.abspath(args.folder)
    results: List[Result] = []

    if not os.path.isdir(folder):
        results.append(needs_data("00_data folder",
                                  f"folder does not exist or is not a directory: {folder}",
                                  rule=_RULE))
        print_results("vault-audit", results)
        return 0

    files = _walk_files(folder)
    if not files:
        results.append(needs_data("00_data contents", f"folder is empty: {folder}", rule=_RULE))
        print_results("vault-audit", results)
        return 0

    # Bucket files by category (a file may match more than one; count once per category).
    buckets: Dict[str, List[str]] = {k: [] for k in _CATEGORY_PATTERNS}
    for rel in files:
        for cat, pats in _CATEGORY_PATTERNS.items():
            if _matches(rel, pats):
                buckets[cat].append(rel)

    # Distinct fiscal years among ARs / distinct quarters among transcripts give a
    # better count than raw file count (dedupes multiple copies of the same period).
    ar_years = {parse_fiscal_year(x) for x in buckets["annual_reports"]}
    ar_years.discard(None)
    cc_quarters = set()
    for x in buckets["concall_transcripts"]:
        q = parse_quarter(x)
        if q:
            cc_quarters.add(q.label)

    def report_min(cat: str, present: int, floor: dict):
        label = floor["label"]
        need = floor["min"]
        if present >= need:
            results.append(passed(cat, f"{present} present (floor {label})",
                                  value=present, threshold=need, rule=_RULE))
        else:
            results.append(needs_data(cat,
                                      f"only {present} present; floor is {label}",
                                      rule=_RULE))

    floor = specs.VAULT_TIER1_FLOOR

    # Annual reports: count distinct fiscal years if detectable, else raw files.
    ar_count = len(ar_years) if ar_years else len(buckets["annual_reports"])
    report_min("annual_reports", ar_count, floor["annual_reports"])

    # Concall transcripts: 8-12 band.
    cc_count = len(cc_quarters) if cc_quarters else len(buckets["concall_transcripts"])
    cc_floor = floor["concall_transcripts"]
    if cc_count >= cc_floor["min"]:
        if cc_count <= cc_floor["max"]:
            results.append(passed("concall_transcripts",
                                  f"{cc_count} present (floor {cc_floor['label']})",
                                  value=cc_count, rule=_RULE))
        else:
            results.append(flag("concall_transcripts",
                                f"{cc_count} present — above the {cc_floor['label']} band "
                                "(not a gap; just noting)", value=cc_count, rule=_RULE))
    else:
        results.append(needs_data("concall_transcripts",
                                  f"only {cc_count} present; floor is {cc_floor['label']}",
                                  rule=_RULE))

    report_min("rating_rationales", len(buckets["rating_rationales"]), floor["rating_rationales"])

    # Exchange filings: spec floor is "24 months". We can't reliably infer months from
    # filenames, so report the file count and name the limitation honestly.
    exf = len(buckets["exchange_filings"])
    if exf > 0:
        results.append(flag("exchange_filings",
                            f"{exf} exchange-filing file(s) present; floor is "
                            f"{floor['exchange_filings_months']['label']} — month-coverage "
                            "cannot be verified from filenames alone (manual check)",
                            value=exf, rule=_RULE))
    else:
        results.append(needs_data("exchange_filings",
                                  f"none present; floor is {floor['exchange_filings_months']['label']}",
                                  rule=_RULE))

    # Shareholding pattern across 8 quarters.
    shp_quarters = set()
    for x in buckets["shareholding"]:
        q = parse_quarter(x)
        if q:
            shp_quarters.add(q.label)
    shp_count = len(shp_quarters) if shp_quarters else len(buckets["shareholding"])
    report_min("shareholding", shp_count, floor["shareholding_quarters"])

    report_min("peer_presentations", len(buckets["peer_presentations"]),
               floor["peer_investor_presentations"])

    print_results("vault-audit", results)
    out_csv = os.path.join(os.path.dirname(folder), "vault_audit_result.csv")
    try:
        write_results_csv(out_csv, results)
        print(f"\n  report written: {out_csv}  (folder inspected read-only)")
    except OSError:
        # If we can't write next to the folder, fall back silently — never fail the audit.
        print("\n  (folder inspected read-only)")
    return 0
