"""p2-5 — locked reverse-DCF triage (Section 5.6, Rule 3.3).

Solve the 10-year revenue CAGR `g` implied by today's price. Constants are LOCKED in
specs.py and never chosen here; the solver's only free variable is `g`.

Model (two-stage FCFF reverse-DCF):
  * Base-year NOPAT  = Revenue0 x median(EBIT margin, 5yr) x (1 - tax)
  * Revenue grows at g for 10 explicit years.
  * Reinvestment rate = g / ROIC_norm  ->  FCFF_t = NOPAT_t x (1 - g/ROIC_norm)
  * Terminal value at year 10 (Gordon): FCFF_11 / (WACC - terminal_g), with terminal
    reinvestment = terminal_g / ROIC_norm.
  * All flows discounted at WACC. Solve g so that DCF value == current EV.

Required inputs: current EV, current Revenue (base R0, needed to scale FCFF to EV),
5-yr EBIT-margin series, ROIC_norm, and the conservative-expectation CAGR C.
Any missing input -> NEEDS-DATA naming the missing one. Never assume a margin or rate.

NOTE on Revenue0: the spec's prose lists EV, margin series, ROIC_norm and C. The DCF
is, however, unsolvable without a base-year revenue to scale FCFF to an absolute EV,
so this command treats current revenue as a required input and returns NEEDS-DATA
when it is absent — consistent with "never assume". Pass it with --revenue.
"""

from __future__ import annotations

import csv
import os
from typing import List, Optional, Tuple

from .. import specs
from ..core import numeric
from ..core.needsdata import Result, needs_data, passed, flag, error
from ..core.report import print_results, write_results_csv

_RULE = "Section 5.6 / Rule 3.3 (locked reverse-DCF triage)"


# --- the locked model -------------------------------------------------------

def dcf_value_per_revenue(g: float, ebit_margin: float, roic_norm: float) -> float:
    """DCF enterprise value expressed PER UNIT of base-year revenue, for growth g.

    Multiplying this by Revenue0 gives the model EV. Uses the locked constants.
    """
    w = specs.P25_WACC
    gt = specs.P25_TERMINAL_GROWTH
    tax = specs.P25_TAX_RATE
    n = specs.P25_EXPLICIT_YEARS

    nopat0_per_rev = ebit_margin * (1.0 - tax)          # per unit revenue
    reinvest_explicit = 1.0 - (g / roic_norm)           # FCFF = NOPAT*(1 - g/ROIC)
    reinvest_terminal = 1.0 - (gt / roic_norm)

    pv_explicit = 0.0
    for t in range(1, n + 1):
        rev_t = (1.0 + g) ** t                          # revenue multiple vs R0
        fcff_t = rev_t * nopat0_per_rev * reinvest_explicit
        pv_explicit += fcff_t / ((1.0 + w) ** t)

    rev_n = (1.0 + g) ** n
    fcff_n1 = rev_n * (1.0 + gt) * nopat0_per_rev * reinvest_terminal
    tv_n = fcff_n1 / (w - gt)
    pv_terminal = tv_n / ((1.0 + w) ** n)

    return pv_explicit + pv_terminal


def solve_implied_growth(ev: float, revenue0: float, ebit_margin: float,
                         roic_norm: float) -> Tuple[Optional[float], str]:
    """Solve for the implied 10-yr revenue CAGR g such that model EV == current EV.

    Scans g upward and bisects the first sign change of (model_EV - EV); this yields
    the smallest (economically meaningful) implied growth even where the value
    function is non-monotonic near g≈ROIC. Returns (g, note) or (None, reason).
    """
    if revenue0 <= 0:
        return None, "current revenue must be positive"
    if roic_norm <= 0:
        return None, "ROIC_norm must be positive"

    target = ev / revenue0

    def f(g: float) -> float:
        return dcf_value_per_revenue(g, ebit_margin, roic_norm) - target

    lo = specs.P25_SOLVER_G_LOW
    hi = specs.P25_SOLVER_G_HIGH
    steps = 1200
    prev_g = lo
    prev_f = f(lo)
    for i in range(1, steps + 1):
        g = lo + (hi - lo) * i / steps
        cur_f = f(g)
        if prev_f == 0.0:
            return prev_g, "exact"
        if (prev_f < 0) != (cur_f < 0):
            # bracket [prev_g, g] — bisection
            a, b, fa = prev_g, g, prev_f
            for _ in range(specs.P25_SOLVER_MAX_ITER):
                m = 0.5 * (a + b)
                fm = f(m)
                if abs(fm) < specs.P25_SOLVER_TOL or (b - a) < specs.P25_SOLVER_TOL:
                    return m, "ok"
                if (fa < 0) != (fm < 0):
                    b = m
                else:
                    a, fa = m, fm
            return 0.5 * (a + b), "ok"
        prev_g, prev_f = g, cur_f

    # No sign change in range.
    if prev_f < 0:
        return None, (f"EV implies revenue CAGR above the solver ceiling "
                      f"({hi:.0%}); price is extreme vs the model")
    return None, (f"EV implies revenue CAGR below the solver floor "
                  f"({lo:.0%}); price is extreme vs the model")


# --- input parsing ----------------------------------------------------------

def _parse_margin_series(args) -> Tuple[Optional[List[float]], Optional[str]]:
    """Return (margins_as_fractions, error_message). Accepts --ebit-margin-series
    'a,b,c,...' or --ebit-margin-csv with an 'ebit_margin' column."""
    raw: List[float] = []
    if args.ebit_margin_series:
        try:
            raw = [float(x) for x in args.ebit_margin_series.replace(" ", "").split(",") if x != ""]
        except ValueError:
            return None, "could not parse --ebit-margin-series (expected comma-separated numbers)"
    elif args.ebit_margin_csv:
        if not os.path.exists(args.ebit_margin_csv):
            return None, f"--ebit-margin-csv not found: {args.ebit_margin_csv}"
        with open(args.ebit_margin_csv, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            col = None
            for c in (reader.fieldnames or []):
                if c and c.strip().lower() in ("ebit_margin", "ebit margin", "margin"):
                    col = c
                    break
            if col is None:
                return None, "CSV needs an 'ebit_margin' column"
            for row in reader:
                v = (row.get(col) or "").strip()
                if v:
                    try:
                        raw.append(float(v))
                    except ValueError:
                        pass
    else:
        return None, None  # not supplied at all

    if not raw:
        return None, "EBIT-margin series was empty"
    # Normalise each value to a fraction (accepts 18 or 0.18). The median is taken
    # over whatever is supplied; the spec expects 5 points but fewer still computes.
    fractions = [numeric.to_fraction(v) for v in raw]
    return fractions, None


# --- command entry ----------------------------------------------------------

def run(args) -> int:
    results: List[Result] = []
    out_dir = os.path.abspath(args.out)

    # Collect/validate inputs, emitting a NEEDS-DATA per genuinely missing one.
    missing_inputs: List[str] = []

    ev = args.ev
    if ev is None:
        missing_inputs.append("current EV (--ev)")
    revenue0 = getattr(args, "revenue", None)
    if revenue0 is None:
        missing_inputs.append("current revenue / base R0 (--revenue) — needed to scale FCFF to EV")

    margins, margin_err = _parse_margin_series(args)
    if margin_err:
        missing_inputs.append(margin_err)
    elif margins is None:
        missing_inputs.append("5-yr EBIT-margin series (--ebit-margin-series or --ebit-margin-csv)")

    roic = args.roic_norm
    if roic is None:
        missing_inputs.append("ROIC_norm (--roic-norm)")
    cagr_c = args.conservative_cagr
    if cagr_c is None:
        missing_inputs.append("conservative-expectation CAGR C (--conservative-cagr)")

    if missing_inputs:
        for m in missing_inputs:
            results.append(needs_data("p2.5 input", m, rule=_RULE))
        print_results("p2-5 reverse-DCF triage", results)
        write_results_csv(os.path.join(out_dir, "p2_5_result.csv"), results)
        return 0

    # Normalise units.
    ebit_margin_median = numeric.median(margins)  # type: ignore[arg-type]
    roic_norm = numeric.to_fraction(roic)
    cee = numeric.to_fraction(cagr_c)

    if cee <= 0:
        results.append(needs_data("conservative CAGR C", "C must be positive to apply Rule 3.3",
                                  rule=_RULE))
        print_results("p2-5 reverse-DCF triage", results)
        write_results_csv(os.path.join(out_dir, "p2_5_result.csv"), results)
        return 0

    g, note = solve_implied_growth(ev, revenue0, ebit_margin_median, roic_norm)

    if g is None:
        results.append(needs_data("implied CAGR g", f"solver could not bracket a solution: {note}",
                                  rule=_RULE))
        print_results("p2-5 reverse-DCF triage", results)
        write_results_csv(os.path.join(out_dir, "p2_5_result.csv"), results)
        return 0

    # Verdict per Rule 3.3.
    pess = specs.P25_PESSIMISM_FRACTION * cee
    if g >= cee:
        verdict = specs.P25_VERDICT_ALREADY_PRICED
        res = flag("p2.5 verdict",
                   f"implied g {g:.2%} >= C {cee:.2%} -> STOP / {verdict}",
                   value=g, threshold=cee, rule=_RULE)
    elif g <= pess:
        verdict = specs.P25_VERDICT_PESSIMISM_PRICED
        res = passed("p2.5 verdict",
                     f"implied g {g:.2%} <= 0.60*C {pess:.2%} -> PROCEED / {verdict}",
                     value=g, threshold=pess, rule=_RULE)
    else:
        verdict = specs.P25_VERDICT_INCONCLUSIVE
        res = flag("p2.5 verdict",
                   f"0.60*C {pess:.2%} < implied g {g:.2%} < C {cee:.2%} -> {verdict}",
                   value=g, threshold=(pess, cee), rule=_RULE)
    results.append(res)

    # Echo the inputs used (provenance of the computation).
    results.append(passed("inputs used",
                          f"EV={ev:g}, Revenue0={revenue0:g}, EBIT-margin median="
                          f"{ebit_margin_median:.2%}, ROIC_norm={roic_norm:.2%}, "
                          f"C={cee:.2%}; WACC={specs.P25_WACC:.0%}, term g="
                          f"{specs.P25_TERMINAL_GROWTH:.0%}, tax={specs.P25_TAX_RATE:.1%}",
                          rule=_RULE))

    print_results("p2-5 reverse-DCF triage", results)
    print(f"\n  implied 10-yr revenue CAGR g = {g:.4f}  ({g:.2%})   [{note}]")
    print(f"  verdict: {verdict}")
    write_results_csv(os.path.join(out_dir, "p2_5_result.csv"), results)
    return 0
