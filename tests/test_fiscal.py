"""Tests for core/fiscal.py — Indian FY/quarter normalisation (Section 6.1)."""

import pytest

from cv500.core import fiscal
from cv500.core.fiscal import QuarterRef


@pytest.mark.parametrize("text,expected", [
    ("FY24", 2024),
    ("FY2024", 2024),
    ("FY 2024", 2024),
    ("F.Y. 2024", 2024),
    ("2023-24", 2024),
    ("2023-2024", 2024),
    ("2023/24", 2024),
    ("AR 2024", 2024),
    ("AR2024", 2024),
    ("Annual Report 2023-24", 2024),
    ("Annual Report 2024", 2024),
    ("FY2025", 2025),
    ("Annual Report 2022-23", 2023),
])
def test_parse_fiscal_year(text, expected):
    assert fiscal.parse_fiscal_year(text) == expected


def test_date_is_not_misread_as_fiscal_range():
    # "2024-06" is a date, not a fiscal range -> must NOT become FY2006.
    assert fiscal.parse_fiscal_year("results 2024-06-30") == 2024


def test_unparseable_returns_none():
    assert fiscal.parse_fiscal_year("quarterly update") is None
    assert fiscal.parse_fiscal_year("") is None
    assert fiscal.parse_fiscal_year(None) is None


@pytest.mark.parametrize("text,fy,q", [
    ("Q1FY25", 2025, 1),
    ("Q1 FY2025", 2025, 1),
    ("Q3 FY24", 2024, 3),
    ("Q4 FY2024", 2024, 4),
    ("FY25 Q2", 2025, 2),
    ("Apr-Jun 2024", 2025, 1),   # Apr-Jun 2024 is Q1 of FY2025
    ("Jan-Mar 2024", 2024, 4),   # Jan-Mar 2024 is Q4 of FY2024
    ("Oct-Dec 2023", 2024, 3),
    ("June 2024", 2025, 1),
])
def test_parse_quarter(text, fy, q):
    qr = fiscal.parse_quarter(text)
    assert qr == QuarterRef(fiscal_year=fy, quarter=q)


def test_parse_quarter_none():
    assert fiscal.parse_quarter("Annual Report 2024") is None
    assert fiscal.parse_quarter("") is None


@pytest.mark.parametrize("month,quarter", [
    (4, 1), (5, 1), (6, 1),
    (7, 2), (8, 2), (9, 2),
    (10, 3), (11, 3), (12, 3),
    (1, 4), (2, 4), (3, 4),
])
def test_month_to_fiscal_quarter(month, quarter):
    assert fiscal.month_to_fiscal_quarter(month) == quarter


@pytest.mark.parametrize("year,month,fy", [
    (2024, 4, 2025),   # Apr 2024 -> FY2025
    (2024, 3, 2024),   # Mar 2024 -> FY2024
    (2024, 12, 2025),  # Dec 2024 -> FY2025
    (2025, 1, 2025),   # Jan 2025 -> FY2025
])
def test_calendar_to_fiscal_year(year, month, fy):
    assert fiscal.calendar_to_fiscal_year(year, month) == fy


def test_latest_n_fiscal_years():
    assert fiscal.latest_n_fiscal_years(2025, 5) == [2025, 2024, 2023, 2022, 2021]
    assert fiscal.latest_n_fiscal_years(2025, 1) == [2025]
    assert fiscal.latest_n_fiscal_years(2025, 0) == []


def test_labels():
    assert fiscal.fy_label(2025) == "FY2025"
    assert fiscal.quarter_label(3) == "Q3"
    assert QuarterRef(2025, 1).label == "Q1_FY2025"
