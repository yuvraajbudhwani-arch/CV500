"""numeric.py — small, auditable pure-Python numerics (no numpy/scipy/pandas).

Provides median, a linear-interpolation percentile (matching numpy's default
'linear'/type-7 method), and a percentile-rank used by the regime gauge.
"""

from __future__ import annotations

from typing import List, Sequence


def median(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("median of empty sequence")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def percentile(values: Sequence[float], p: float) -> float:
    """The p-th percentile (0<=p<=100) using linear interpolation between closest
    ranks — identical to numpy.percentile(..., interpolation='linear')."""
    if not values:
        raise ValueError("percentile of empty sequence")
    if not (0.0 <= p <= 100.0):
        raise ValueError("p must be in [0, 100]")
    s = sorted(values)
    n = len(s)
    if n == 1:
        return float(s[0])
    rank = (p / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(s[lo] + (s[hi] - s[lo]) * frac)


def percentile_rank(values: Sequence[float], x: float) -> float:
    """Where does x sit within `values`, as a 0-100 percentile?

    Uses the 'mean' convention: 100 * (count(<x) + 0.5*count(==x)) / n. This is a
    stable, standard definition for 'what percentile is the current reading'.
    """
    if not values:
        raise ValueError("percentile_rank of empty sequence")
    n = len(values)
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    return 100.0 * (below + 0.5 * equal) / n


def to_fraction(x: float, *, percent_threshold: float = 1.5) -> float:
    """Normalise a possibly-percent value to a fraction.

    Many operator inputs (margins, ROIC, CAGR) may be entered as 18 (meaning 18%)
    or 0.18. If |x| > percent_threshold we treat it as a percentage and divide by
    100. The threshold of 1.5 safely distinguishes 0.18 (fraction) from 18 (percent)
    while never misreading a plausible fraction.
    """
    return x / 100.0 if abs(x) > percent_threshold else x
