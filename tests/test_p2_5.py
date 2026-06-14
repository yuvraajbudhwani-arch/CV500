"""Tests for the p2-5 reverse-DCF solver and verdict (Section 5.6, Rule 3.3)."""

import math

import pytest

from cv500 import specs
from cv500.commands.p2_5 import dcf_value_per_revenue, solve_implied_growth


def test_locked_constants_unchanged():
    # Guard the LOCKED constants so a refactor can't silently move them.
    assert specs.P25_WACC == 0.14
    assert specs.P25_TERMINAL_GROWTH == 0.04
    assert specs.P25_TAX_RATE == 0.252
    assert specs.P25_EXPLICIT_YEARS == 10
    assert specs.P25_PESSIMISM_FRACTION == 0.60


@pytest.mark.parametrize("true_g", [-0.10, 0.0, 0.05, 0.10, 0.15, 0.18])
def test_solver_round_trips(true_g):
    """Build an EV from a known g, then solve back — must recover g."""
    m, roic, R0 = 0.15, 0.20, 1000.0
    ev = dcf_value_per_revenue(true_g, m, roic) * R0
    g, note = solve_implied_growth(ev, R0, m, roic)
    assert g is not None
    assert math.isclose(g, true_g, abs_tol=1e-5)


def test_hand_checked_value():
    """A hand-verifiable point: g=0, so revenue is flat at R0 forever.

    Per-revenue NOPAT = m*(1-tax); reinvestment = 1 - 0/ROIC = 1 (no growth, no reinvest
    drag); terminal reinvestment = 1 - gt/ROIC. Compute the closed form and compare.
    """
    m, roic = 0.15, 0.20
    w, gt, tax, n = 0.14, 0.04, 0.252, 10
    nopat = m * (1 - tax)
    # explicit: flat NOPAT for 10 years (g=0 -> revenue multiple 1, reinvest 1)
    pv_explicit = sum(nopat / (1 + w) ** t for t in range(1, n + 1))
    # terminal: FCFF_11 = 1*(1+gt)*nopat*(1 - gt/roic)
    fcff_n1 = (1 + gt) * nopat * (1 - gt / roic)
    tv = fcff_n1 / (w - gt)
    pv_terminal = tv / (1 + w) ** n
    expected = pv_explicit + pv_terminal
    assert math.isclose(dcf_value_per_revenue(0.0, m, roic), expected, rel_tol=1e-9)


def test_value_increases_with_growth_in_range():
    m, roic = 0.15, 0.20
    vals = [dcf_value_per_revenue(g, m, roic) for g in (0.0, 0.05, 0.10, 0.15)]
    assert vals == sorted(vals)


def test_solver_rejects_bad_inputs():
    g, note = solve_implied_growth(1000, 0, 0.15, 0.20)
    assert g is None and "revenue" in note
    g, note = solve_implied_growth(1000, 1000, 0.15, 0.0)
    assert g is None and "ROIC" in note


def _verdict(g, c):
    """Mirror the Rule 3.3 banding used by the command for assertion convenience."""
    pess = specs.P25_PESSIMISM_FRACTION * c
    if g >= c:
        return specs.P25_VERDICT_ALREADY_PRICED
    if g <= pess:
        return specs.P25_VERDICT_PESSIMISM_PRICED
    return specs.P25_VERDICT_INCONCLUSIVE


def test_verdict_bands():
    c = 0.12
    assert _verdict(0.13, c) == specs.P25_VERDICT_ALREADY_PRICED      # g >= C
    assert _verdict(0.12, c) == specs.P25_VERDICT_ALREADY_PRICED      # g == C
    assert _verdict(0.05, c) == specs.P25_VERDICT_PESSIMISM_PRICED    # g <= 0.6C (0.072)
    assert _verdict(0.072, c) == specs.P25_VERDICT_PESSIMISM_PRICED   # g == 0.6C
    assert _verdict(0.10, c) == specs.P25_VERDICT_INCONCLUSIVE        # between
