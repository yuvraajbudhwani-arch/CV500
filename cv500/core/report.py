"""report.py — uniform console printing and CSV writing for Result lists.

Shared by the deterministic commands (p0-check, regime, liquidity, p2-5,
monthly-scan, vault-audit, screen-ingest) so every command surfaces PASS / KILL /
FLAG / NEEDS-DATA the same way, with provenance, and writes a machine-readable CSV.
"""

from __future__ import annotations

import csv
import os
from typing import List, Optional

from .needsdata import Result, summarize

_GLYPH = {
    "PASS": "PASS  ",
    "KILL": "KILL  ",
    "FLAG": "FLAG  ",
    "NEEDS-DATA": "NEEDS-DATA",
    "ERROR": "ERROR ",
}


def print_results(title: str, results: List[Result]) -> None:
    print(f"\n== {title} ==")
    if not results:
        print("  (no checks ran)")
        return
    for r in results:
        line = f"  [{_GLYPH.get(r.status, r.status)}] {r.name}"
        if r.detail:
            line += f" — {r.detail}"
        print(line)
        if r.rule:
            print(f"             rule: {r.rule}")
        if r.provenance is not None:
            print(f"             src:  {r.provenance.source_url} "
                  f"@ {r.provenance.retrieval_datetime}")
    counts = summarize(results)
    summary = ", ".join(f"{k}={v}" for k, v in counts.items() if v)
    print(f"  -- summary: {summary or 'none'}")


def write_results_csv(path: str, results: List[Result]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    cols = ["name", "status", "detail", "value", "threshold", "rule",
            "source_url", "source_site", "retrieval_datetime"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in results:
            d = r.to_dict()
            w.writerow([d.get(c, "") for c in cols])


def overall_status(results: List[Result]) -> str:
    """Roll up a list of results to one headline word.

    KILL dominates; then NEEDS-DATA; then FLAG; else PASS. (Commands that screen
    treat any KILL as a kill; monitoring commands map FLAG->interrupt themselves.)
    """
    statuses = {r.status for r in results}
    if "KILL" in statuses:
        return "KILL"
    if "ERROR" in statuses:
        return "ERROR"
    if "NEEDS-DATA" in statuses:
        return "NEEDS-DATA"
    if "FLAG" in statuses:
        return "FLAG"
    return "PASS"
