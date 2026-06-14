"""liquidity — stressed-liquidity exit budget (Section 5.5, Rule 7.4).

Per-name exit budget = 10 trading days x 20% participation x P25(daily delivered
value, trailing 2 years). A position's value at market must remain within that budget.

Inputs:
  * --delivered-csv : daily delivered value (columns date, delivered_value); the tool
    computes P25 over the supplied series (intended ~2 trading years).
  * --position-value (optional) : tests whether the position fits the budget.
  * --ticker : recorded for provenance; live NSE/BSE delivered-value pull is deferred
    (NSE blocks generic clients), so a CSV is required for now.

Missing the delivered-value data (hence P25) -> NEEDS-DATA.
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

_RULE = "Section 5.5 / Rule 7.4 (stressed liquidity)"


def _delivered_values_from_csv(path: str) -> Tuple[Optional[List[float]], str]:
    if not os.path.exists(path):
        return None, f"delivered-value CSV not found: {path}"
    vals: List[float] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = {(c or "").strip().lower(): c for c in (reader.fieldnames or [])}
        col = next((fields[k] for k in fields if k in
                    ("delivered_value", "delivered value", "deliverable_value",
                     "delivery_value", "value", "delivered")), None)
        if col is None:
            return None, "CSV needs a 'delivered_value' column"
        for row in reader:
            v = (row.get(col) or "").strip().replace(",", "")
            if v:
                try:
                    vals.append(float(v))
                except ValueError:
                    pass
    if len(vals) < 2:
        return None, "delivered-value CSV had too few valid rows"
    return vals, f"{len(vals)} daily observations"


def run(args) -> int:
    out_dir = os.path.abspath(args.out)
    results: List[Result] = []

    if not args.delivered_csv:
        results.append(needs_data(
            "daily delivered value",
            "~2yr of daily security-wise delivered value (P25 input). Live NSE/BSE "
            "pull is deferred — supply --delivered-csv. (ticker="
            f"{args.ticker or 'n/a'})", rule=_RULE))
        print_results("stressed liquidity", results)
        write_results_csv(os.path.join(out_dir, "liquidity_result.csv"), results)
        return 0

    vals, note = _delivered_values_from_csv(args.delivered_csv)
    if vals is None:
        results.append(needs_data("daily delivered value", note, rule=_RULE))
        print_results("stressed liquidity", results)
        write_results_csv(os.path.join(out_dir, "liquidity_result.csv"), results)
        return 0

    p25 = numeric.percentile(vals, specs.LIQUIDITY_DELIVERED_VALUE_PERCENTILE)
    budget = (specs.LIQUIDITY_EXIT_TRADING_DAYS
              * specs.LIQUIDITY_PARTICIPATION_RATE
              * p25)
    prov = stamp(os.path.abspath(args.delivered_csv), source_site="company",
                 note=f"operator-supplied delivered-value series ({note})")

    results.append(passed(
        "exit budget",
        f"P25(daily delivered value)={p25:,.0f}; budget = "
        f"{specs.LIQUIDITY_EXIT_TRADING_DAYS} days x "
        f"{specs.LIQUIDITY_PARTICIPATION_RATE:.0%} x P25 = {budget:,.0f}",
        value=budget, rule=_RULE, provenance=prov))

    if args.position_value is not None:
        fits = args.position_value <= budget
        msg = (f"position value {args.position_value:,.0f} "
               f"{'<=' if fits else '>'} budget {budget:,.0f}")
        if fits:
            results.append(passed("position fit", msg + " -> fits exit budget",
                                  value=args.position_value, threshold=budget, rule=_RULE))
        else:
            results.append(flag("position fit", msg + " -> EXCEEDS exit budget",
                                value=args.position_value, threshold=budget, rule=_RULE))

    print_results("stressed liquidity", results)
    print(f"\n  P25 delivered value = {p25:,.0f}")
    print(f"  exit budget         = {budget:,.0f}")
    if args.position_value is not None:
        print(f"  position value      = {args.position_value:,.0f}  "
              f"({'FITS' if args.position_value <= budget else 'EXCEEDS'})")
    write_results_csv(os.path.join(out_dir, "liquidity_result.csv"), results)
    return 0
