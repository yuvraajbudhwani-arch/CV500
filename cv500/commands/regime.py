"""regime — produce the regime verdict FROTHY / NORMAL / CHEAP (Section 5.4, Rule 7.3).

Inputs (either):
  * the two percentiles directly (--pe-pctile, --pb-pctile), OR
  * a 10-yr monthly series CSV of Smallcap-250 P/E and P/B; the tool computes the
    current reading's percentile within the supplied series.

Verdict:
  FROTHY = both percentiles >= 80th
  CHEAP  = both percentiles <= 25th
  NORMAL = anything else, including when the two gauges disagree.
Missing either percentile -> NEEDS-DATA.
"""

from __future__ import annotations

import csv
import os
from typing import List, Optional, Tuple

from .. import specs
from ..core import numeric
from ..core.needsdata import Result, needs_data, passed, flag
from ..core.provenance import stamp
from ..core.report import print_results, write_results_csv

_RULE = "Section 5.4 / Rule 7.3 (regime gauge)"


def _percentiles_from_csv(path: str) -> Tuple[Optional[float], Optional[float], str]:
    """Compute the current (latest-row) P/E and P/B percentile vs the full series.

    Expects columns: date, pe, pb (case-insensitive; 'price_earnings'/'pe_ratio' etc
    also accepted). The latest row (by file order; last non-empty) is the current
    reading. Returns (pe_pctile, pb_pctile, note)."""
    if not os.path.exists(path):
        return None, None, f"series CSV not found: {path}"
    pe_vals: List[float] = []
    pb_vals: List[float] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = {(c or "").strip().lower(): c for c in (reader.fieldnames or [])}
        pe_col = next((fields[k] for k in fields if k in
                       ("pe", "p/e", "pe_ratio", "price_earnings", "trailing_pe")), None)
        pb_col = next((fields[k] for k in fields if k in
                       ("pb", "p/b", "pb_ratio", "price_book", "trailing_pb")), None)
        if pe_col is None or pb_col is None:
            return None, None, "series CSV needs 'pe' and 'pb' columns"
        for row in reader:
            try:
                pe = float((row.get(pe_col) or "").strip())
                pb = float((row.get(pb_col) or "").strip())
            except ValueError:
                continue
            pe_vals.append(pe)
            pb_vals.append(pb)
    if len(pe_vals) < 2 or len(pb_vals) < 2:
        return None, None, "series CSV had too few valid rows to rank a percentile"
    cur_pe, cur_pb = pe_vals[-1], pb_vals[-1]
    pe_pct = numeric.percentile_rank(pe_vals, cur_pe)
    pb_pct = numeric.percentile_rank(pb_vals, cur_pb)
    note = (f"computed from {len(pe_vals)} rows; current P/E={cur_pe:g} "
            f"(pctile {pe_pct:.1f}), P/B={cur_pb:g} (pctile {pb_pct:.1f})")
    return pe_pct, pb_pct, note


def classify_regime(pe_pct: float, pb_pct: float) -> str:
    hi = specs.REGIME_FROTHY_MIN_PCTILE
    lo = specs.REGIME_CHEAP_MAX_PCTILE
    if pe_pct >= hi and pb_pct >= hi:
        return "FROTHY"
    if pe_pct <= lo and pb_pct <= lo:
        return "CHEAP"
    return "NORMAL"


def run(args) -> int:
    out_dir = os.path.abspath(args.out)
    results: List[Result] = []

    pe_pct = args.pe_pctile
    pb_pct = args.pb_pctile
    source_note = "percentiles supplied directly"
    prov = None

    if (pe_pct is None or pb_pct is None) and args.series_csv:
        cpe, cpb, note = _percentiles_from_csv(args.series_csv)
        if cpe is None or cpb is None:
            results.append(needs_data("regime inputs", note, rule=_RULE))
            print_results("regime gauge", results)
            write_results_csv(os.path.join(out_dir, "regime_result.csv"), results)
            return 0
        pe_pct = cpe if pe_pct is None else pe_pct
        pb_pct = cpb if pb_pct is None else pb_pct
        source_note = note
        prov = stamp(os.path.abspath(args.series_csv), source_site="company",
                     note="operator-supplied 10yr monthly series")

    # Validate presence — name exactly which percentile is missing.
    if pe_pct is None:
        results.append(needs_data("P/E percentile",
                                  "Smallcap-250 trailing P/E percentile (vs 10yr monthly "
                                  "series) — supply --pe-pctile or --series-csv", rule=_RULE))
    if pb_pct is None:
        results.append(needs_data("P/B percentile",
                                  "Smallcap-250 trailing P/B percentile (vs 10yr monthly "
                                  "series) — supply --pb-pctile or --series-csv", rule=_RULE))
    if pe_pct is None or pb_pct is None:
        print_results("regime gauge", results)
        write_results_csv(os.path.join(out_dir, "regime_result.csv"), results)
        return 0

    for label, val in (("P/E percentile", pe_pct), ("P/B percentile", pb_pct)):
        if not (0.0 <= val <= 100.0):
            results.append(needs_data(label, f"percentile {val} is outside [0,100]", rule=_RULE))
            print_results("regime gauge", results)
            write_results_csv(os.path.join(out_dir, "regime_result.csv"), results)
            return 0

    verdict = classify_regime(pe_pct, pb_pct)
    detail = (f"{specs.REGIME_INDEX}: P/E pctile={pe_pct:.1f}, P/B pctile={pb_pct:.1f} "
              f"(FROTHY if both>={specs.REGIME_FROTHY_MIN_PCTILE:.0f}, "
              f"CHEAP if both<={specs.REGIME_CHEAP_MAX_PCTILE:.0f}) -> {verdict}. {source_note}")
    res = passed("regime", detail, value=verdict, rule=_RULE, provenance=prov) if verdict == "NORMAL" \
        else flag("regime", detail, value=verdict, rule=_RULE, provenance=prov)
    results.append(res)

    print_results("regime gauge", results)
    print(f"\n  REGIME: {verdict}   (P/E pctile {pe_pct:.1f}, P/B pctile {pb_pct:.1f})")
    write_results_csv(os.path.join(out_dir, "regime_result.csv"), results)
    return 0
