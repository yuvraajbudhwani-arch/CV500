"""Tests for core/numeric.py — pure-Python median / percentile / percentile_rank."""

import math

import pytest

from cv500.core import numeric


def test_median():
    assert numeric.median([3, 1, 2]) == 2
    assert numeric.median([1, 2, 3, 4]) == 2.5
    assert numeric.median([5]) == 5


def test_percentile_matches_linear_method():
    # numpy.percentile(range(1..100), 25) == 25.75 with linear interpolation.
    data = list(range(1, 101))
    assert math.isclose(numeric.percentile(data, 25), 25.75, rel_tol=1e-9)
    assert math.isclose(numeric.percentile(data, 50), 50.5, rel_tol=1e-9)
    assert numeric.percentile([10, 20], 0) == 10
    assert numeric.percentile([10, 20], 100) == 20


def test_percentile_p25_liquidity_shape():
    # Simple symmetric set: P25 of 1..4 with linear interp = 1.75.
    assert math.isclose(numeric.percentile([1, 2, 3, 4], 25), 1.75, rel_tol=1e-9)


def test_percentile_rank():
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    # 10 is the max -> rank counts all below + half equal = (9 + 0.5)/10*100 = 95
    assert numeric.percentile_rank(data, 10) == 95.0
    # value below all -> 0
    assert numeric.percentile_rank(data, 0) == 0.0


def test_to_fraction():
    assert numeric.to_fraction(0.18) == 0.18      # already a fraction
    assert numeric.to_fraction(18) == 0.18        # percent -> fraction
    assert numeric.to_fraction(1.0) == 1.0        # boundary stays
    assert math.isclose(numeric.to_fraction(14), 0.14)


def test_empty_raises():
    with pytest.raises(ValueError):
        numeric.median([])
    with pytest.raises(ValueError):
        numeric.percentile([], 50)
