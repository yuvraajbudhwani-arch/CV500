"""fiscal.py — Indian fiscal-year and quarter normalisation.

Indian fiscal years run April–March and are labelled by the ENDING year:
    FY2025 = Apr 2024 – Mar 2025.

Fiscal quarters (Section 6.1):
    Q1 = Apr–Jun, Q2 = Jul–Sep, Q3 = Oct–Dec, Q4 = Jan–Mar.

This module turns the many notations seen on IR sites into a canonical fiscal year
(an int = the ending year) and, for quarterly items, a (fiscal_year, quarter) pair.

Handled notations include (Section 6.1):
    FY24, FY2024, FY 2024, 2023-24, 2023-2024, AR 2024, Annual Report 2023-24,
    Q1FY25, Q1 FY2025, Q3 FY24, Apr-Jun 2024.

Design note: parsing is deliberately conservative. Ambiguous strings that could be
calendar dates (e.g. "2024-06-30") are NOT silently turned into fiscal ranges — a
"YYYY-YY" range only counts when the second part is exactly the next year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Quarter <-> month mapping
# ---------------------------------------------------------------------------

# Indian fiscal quarter for a calendar month number (1-12).
_MONTH_TO_FQ = {
    4: 1, 5: 1, 6: 1,      # Q1 Apr-Jun
    7: 2, 8: 2, 9: 2,      # Q2 Jul-Sep
    10: 3, 11: 3, 12: 3,   # Q3 Oct-Dec
    1: 4, 2: 4, 3: 4,      # Q4 Jan-Mar
}

_MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def month_to_fiscal_quarter(month: int) -> int:
    """Map a calendar month (1-12) to its Indian fiscal quarter (1-4)."""
    if month not in _MONTH_TO_FQ:
        raise ValueError(f"month must be 1-12, got {month}")
    return _MONTH_TO_FQ[month]


def calendar_to_fiscal_year(cal_year: int, month: int) -> int:
    """The fiscal year (ending year) that a calendar (year, month) falls in.

    Apr-Dec belong to the *next* calendar year's FY; Jan-Mar stay in the same.
    e.g. (2024, 4) -> FY2025;  (2024, 1) -> FY2024.
    """
    return cal_year + 1 if month >= 4 else cal_year


# ---------------------------------------------------------------------------
# Canonical labels
# ---------------------------------------------------------------------------

def fy_label(fiscal_year: int) -> str:
    """1995..2099 -> 'FY1995'..'FY2099'."""
    return f"FY{fiscal_year}"


def quarter_label(quarter: int) -> str:
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    return f"Q{quarter}"


def latest_n_fiscal_years(anchor_fy: int, n: int) -> List[int]:
    """[anchor_fy, anchor_fy-1, ..., anchor_fy-n+1] — newest first."""
    if n < 1:
        return []
    return [anchor_fy - i for i in range(n)]


@dataclass(frozen=True)
class QuarterRef:
    fiscal_year: int
    quarter: int

    @property
    def label(self) -> str:
        return f"{quarter_label(self.quarter)}_{fy_label(self.fiscal_year)}"


# ---------------------------------------------------------------------------
# Helpers to widen 2-digit years
# ---------------------------------------------------------------------------

def _widen_year(token: str) -> Optional[int]:
    """'24' -> 2024, '2024' -> 2024. Returns None if not a plausible FY year."""
    token = token.strip()
    if not token.isdigit():
        return None
    if len(token) == 2:
        return 2000 + int(token)
    if len(token) == 4:
        y = int(token)
        # Restrict to the modern era we actually deal with.
        return y if 1990 <= y <= 2099 else None
    return None


# ---------------------------------------------------------------------------
# Fiscal-year parsing
# ---------------------------------------------------------------------------

# "2023-24", "2023-2024", "2023/24" (and en/em dashes). Validated below.
_RANGE_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})\s*[-/–—]\s*(\d{2,4})(?!\d)")
# "FY24", "FY 2024", "FY'24", "F.Y. 2024"
_FY_RE = re.compile(r"(?<![A-Za-z])F\.?\s*Y\.?\s*'?\s*(\d{2,4})(?!\d)", re.IGNORECASE)
# "AR 2024", "Annual Report 2024"  (range form handled by _RANGE_RE first)
_AR_RE = re.compile(
    r"(?:annual\s*report|\bAR)\s*[:#\-]?\s*(19\d{2}|20\d{2})(?!\d)", re.IGNORECASE
)
# bare 4-digit year, last resort
_BARE_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")


def _range_ending_year(first: str, second: str) -> Optional[int]:
    """For a 'YYYY-YY'/'YYYY-YYYY' fiscal range, return the ending year IFF it is
    exactly first+1 (which is what a real fiscal-year range looks like). This is the
    guard that stops '2024-06' (a date) from being read as a fiscal range."""
    f = int(first)
    if len(second) == 2:
        end = (f // 100) * 100 + int(second)
        # handle century roll, e.g. 1999-00 -> 2000
        if end < f:
            end += 100
    elif len(second) == 4:
        end = int(second)
    else:
        return None
    return end if end == f + 1 else None


def parse_fiscal_year(text: Optional[str]) -> Optional[int]:
    """Extract a canonical fiscal year (ending year) from arbitrary label text.

    Returns None when no fiscal year can be confidently identified. Tried in order
    of specificity so the most reliable interpretation wins.
    """
    if not text:
        return None

    # 1) Explicit fiscal range "YYYY-YY" / "YYYY-YYYY".
    m = _RANGE_RE.search(text)
    if m:
        end = _range_ending_year(m.group(1), m.group(2))
        if end is not None:
            return end

    # 2) FY-prefixed.
    m = _FY_RE.search(text)
    if m:
        y = _widen_year(m.group(1))
        if y is not None:
            return y

    # 3) "AR <year>" / "Annual Report <year>".
    m = _AR_RE.search(text)
    if m:
        y = _widen_year(m.group(1))
        if y is not None:
            return y

    # 4) Bare 4-digit year (least specific).
    m = _BARE_YEAR_RE.search(text)
    if m:
        return _widen_year(m.group(1))

    return None


# ---------------------------------------------------------------------------
# Quarter parsing
# ---------------------------------------------------------------------------

# "Q1FY25", "Q1 FY2025", "Q3 FY24", "Q1 F.Y. 25"
_QFY_RE = re.compile(
    r"Q\s*([1-4])\s*[,\-]?\s*F\.?\s*Y\.?\s*'?\s*(\d{2,4})(?!\d)", re.IGNORECASE
)
# Reverse order "FY25 Q1"
_FYQ_RE = re.compile(
    r"F\.?\s*Y\.?\s*'?\s*(\d{2,4})\s*[,\-]?\s*Q\s*([1-4])(?!\d)", re.IGNORECASE
)
# Month range "Apr-Jun 2024", "Jan - Mar 2024"
_MONTH_RANGE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*"
    r"[-–—]\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*"
    r"(19\d{2}|20\d{2})",
    re.IGNORECASE,
)
# Single month + year "June 2024", "Jun 2024"
_MONTH_SINGLE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*'?\s*(19\d{2}|20\d{2})",
    re.IGNORECASE,
)


def parse_quarter(text: Optional[str]) -> Optional[QuarterRef]:
    """Extract a (fiscal_year, quarter) from arbitrary label text, or None.

    Handles Q#FY## forms and month-based forms. For a month or month-range, the
    *first* month determines the quarter and the printed year is the calendar year
    of that month (converted to fiscal year).
    """
    if not text:
        return None

    # 1) Q#-FY# in either order.
    m = _QFY_RE.search(text)
    if m:
        q = int(m.group(1))
        fy = _widen_year(m.group(2))
        if fy is not None:
            return QuarterRef(fiscal_year=fy, quarter=q)

    m = _FYQ_RE.search(text)
    if m:
        fy = _widen_year(m.group(1))
        q = int(m.group(2))
        if fy is not None:
            return QuarterRef(fiscal_year=fy, quarter=q)

    # 2) Month range "Apr-Jun 2024".
    m = _MONTH_RANGE_RE.search(text)
    if m:
        first_month = _MONTH_NAMES.get(m.group(1).lower()[:4]) or _MONTH_NAMES.get(m.group(1).lower()[:3])
        cal_year = int(m.group(3))
        if first_month:
            q = month_to_fiscal_quarter(first_month)
            fy = calendar_to_fiscal_year(cal_year, first_month)
            return QuarterRef(fiscal_year=fy, quarter=q)

    # 3) Single month + year "June 2024".
    m = _MONTH_SINGLE_RE.search(text)
    if m:
        month = _MONTH_NAMES.get(m.group(1).lower()[:4]) or _MONTH_NAMES.get(m.group(1).lower()[:3])
        cal_year = int(m.group(2))
        if month:
            q = month_to_fiscal_quarter(month)
            fy = calendar_to_fiscal_year(cal_year, month)
            return QuarterRef(fiscal_year=fy, quarter=q)

    return None
