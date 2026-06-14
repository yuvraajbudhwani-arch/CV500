"""naming.py — company-name cleaning and deterministic file/zip naming.

Spec (Section 6.1):
  {NAME} = company name with corporate suffix removed (Ltd, Limited, Pvt, Private,
  Inc, Corporation), punctuation stripped, spaces -> underscores.
  Required example, matched exactly here:  "abc ltd."  ->  ABC_5yr_AR_EC-Transcripts.zip

That example fixes the convention: the cleaned name is UPPER-CASED (abc -> ABC).
"""

from __future__ import annotations

import re
from typing import Optional

from .. import specs
from .fiscal import QuarterRef, fy_label, quarter_label

# Suffix tokens (lower-cased) stripped from the END of a company name.
_SUFFIX_TOKENS = {s.lower() for s in specs.COMPANY_NAME_SUFFIXES}
# Common spelling variants of the same suffixes seen on Indian filings.
_SUFFIX_TOKENS |= {"co", "corp", "ltd", "pvt"}


def clean_company_name(raw: Optional[str], fallback: str = "COMPANY") -> str:
    """Turn a raw company name into the canonical {NAME} token.

    Steps: split into alphanumeric word tokens (this strips all punctuation),
    drop trailing corporate-suffix tokens, join with underscores, upper-case.

    >>> clean_company_name("abc ltd.")
    'ABC'
    >>> clean_company_name("Reliance Industries Limited")
    'RELIANCE_INDUSTRIES'
    >>> clean_company_name("Pidilite Industries Ltd")
    'PIDILITE_INDUSTRIES'
    """
    if not raw:
        return fallback

    # Tokenise on any non-alphanumeric run -> strips punctuation, splits words.
    tokens = re.findall(r"[A-Za-z0-9]+", raw)
    if not tokens:
        return fallback

    # Drop trailing corporate-suffix tokens (handles "Pvt Ltd", "Private Limited").
    while tokens and tokens[-1].lower() in _SUFFIX_TOKENS:
        tokens.pop()

    if not tokens:
        return fallback

    return "_".join(tokens).upper()


def zip_name(name: str, years: int) -> str:
    """'{NAME}_{n}yr_AR_EC-Transcripts.zip' — uses the actual year count."""
    return f"{name}_{years}yr_AR_EC-Transcripts.zip"


def ar_filename(name: str, fiscal_year: int) -> str:
    """'{NAME}_AR_FY2025.pdf'."""
    return f"{name}_AR_{fy_label(fiscal_year)}.pdf"


def concall_filename(name: str, qref: QuarterRef) -> str:
    """'{NAME}_Concall_Q1_FY2025.pdf'."""
    return f"{name}_Concall_{quarter_label(qref.quarter)}_{fy_label(qref.fiscal_year)}.pdf"


def safe_filename(text: str) -> str:
    """Sanitise an arbitrary string for use as a filesystem name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return cleaned or "file"
