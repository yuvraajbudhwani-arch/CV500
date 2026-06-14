"""pdfval.py — validate a downloaded PDF before keeping it (Section 6.1).

Two jobs:
  1. Confirm a file is the document we think it is — an annual report "looks like"
     one (contains "Annual Report" / "Notice of AGM" / "Directors' Report" /
     financial statements); a transcript "looks like" one (contains "Earnings Call" /
     "Conference Call" / "Transcript" / "Moderator" / speaker turns).
  2. Extract the document's own stated fiscal year / quarter, so the caller can
     cross-check it against the year inferred from the link and PREFER the document's
     own stated period when they disagree.

Text extraction uses pypdf and is capped to a handful of pages (cover + a few) — the
cover and first pages carry the title, year, and document-type cues we need.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Optional

from .fiscal import QuarterRef, parse_fiscal_year, parse_quarter

KIND_AR = "Annual Report"
KIND_TRANSCRIPT = "Earnings Call Transcript"
KIND_UNKNOWN = "Unknown"

# Distinct phrases that signal an annual report.
_AR_KEYWORDS = (
    "annual report", "notice of agm", "notice of annual general meeting",
    "directors' report", "director's report", "board's report", "boards' report",
    "independent auditor", "auditor's report", "balance sheet",
    "statement of profit and loss", "cash flow statement", "corporate overview",
    "management discussion and analysis", "standalone financial",
    "consolidated financial", "report of the board of directors",
)
# Distinct phrases that signal an earnings-call transcript.
_TRANSCRIPT_KEYWORDS = (
    "earnings call", "earnings conference call", "conference call", "transcript",
    "moderator", "ladies and gentlemen", "thank you for joining",
    "question-and-answer", "question and answer session", "q&a session",
    "first question", "next question", "on the call", "good morning",
    "good evening", "good afternoon",
)

_MAX_PAGES_FOR_TEXT = 8


@dataclass
class PdfValidation:
    is_pdf: bool
    kind: str = KIND_UNKNOWN
    matches_expected: bool = False
    stated_fiscal_year: Optional[int] = None
    stated_quarter: Optional[QuarterRef] = None
    status: str = "unverified"        # 'ok' | 'unverified' (manifest column)
    notes: List[str] = field(default_factory=list)
    ar_hits: int = 0
    transcript_hits: int = 0


def _looks_like_pdf(content: bytes) -> bool:
    return bool(content) and content[:5].startswith(b"%PDF-")


def extract_text(content: bytes, max_pages: int = _MAX_PAGES_FOR_TEXT) -> str:
    """Extract text from the first `max_pages` pages. Returns '' on any failure
    (encrypted, malformed, image-only) — callers treat empty text as 'unverified'."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except Exception:
        return ""
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            try:
                reader.decrypt("")  # try empty-password (common for "owner" locks)
            except Exception:
                return ""
        chunks: List[str] = []
        for page in reader.pages[:max_pages]:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(chunks)
    except (PdfReadError, Exception):
        return ""


def _count_hits(haystack: str, needles) -> int:
    return sum(1 for n in needles if n in haystack)


def validate(content: bytes,
             expected_kind: str,
             expected_fiscal_year: Optional[int] = None,
             expected_quarter: Optional[QuarterRef] = None) -> PdfValidation:
    """Validate `content` against an expected kind / period.

    Never raises — returns a PdfValidation describing what was found. The caller
    decides whether to keep the file for a given grid slot.
    """
    if not _looks_like_pdf(content):
        return PdfValidation(is_pdf=False, status="unverified",
                             notes=["not a PDF (missing %PDF- header)"])

    text = extract_text(content)
    low = text.lower()
    v = PdfValidation(is_pdf=True)

    if not low.strip():
        v.notes.append("no extractable text (scanned/image PDF?) — cannot verify content")
        v.status = "unverified"
        # Still attempt nothing more; kind/period unknown.
        return v

    v.ar_hits = _count_hits(low, _AR_KEYWORDS)
    v.transcript_hits = _count_hits(low, _TRANSCRIPT_KEYWORDS)

    # Classify by keyword dominance (require >=2 distinct hits to claim a kind).
    if v.ar_hits >= 2 and v.ar_hits >= v.transcript_hits:
        v.kind = KIND_AR
    elif v.transcript_hits >= 2 and v.transcript_hits > v.ar_hits:
        v.kind = KIND_TRANSCRIPT
    else:
        v.kind = KIND_UNKNOWN

    # Stated period: look at the first ~2 pages' worth most strongly. We just reuse
    # the full extracted text; the fiscal parsers pick the most specific token.
    first_slice = text[:4000]
    if expected_kind == KIND_TRANSCRIPT or v.kind == KIND_TRANSCRIPT:
        v.stated_quarter = parse_quarter(first_slice) or parse_quarter(text)
        if v.stated_quarter:
            v.stated_fiscal_year = v.stated_quarter.fiscal_year
        else:
            v.stated_fiscal_year = parse_fiscal_year(first_slice) or parse_fiscal_year(text)
    else:
        v.stated_fiscal_year = parse_fiscal_year(first_slice) or parse_fiscal_year(text)

    # Decide matches_expected + status.
    kind_ok = (v.kind == expected_kind)
    if not kind_ok and v.kind == KIND_UNKNOWN:
        v.notes.append(f"content cues inconclusive (AR hits={v.ar_hits}, "
                       f"transcript hits={v.transcript_hits})")

    period_ok = True
    if expected_fiscal_year is not None and v.stated_fiscal_year is not None:
        if v.stated_fiscal_year != expected_fiscal_year:
            period_ok = False
            v.notes.append(
                f"stated FY{v.stated_fiscal_year} differs from link-inferred "
                f"FY{expected_fiscal_year}; preferring document's stated period"
            )
    if (expected_quarter is not None and v.stated_quarter is not None
            and v.stated_quarter != expected_quarter):
        period_ok = False
        v.notes.append(
            f"stated {v.stated_quarter.label} differs from link-inferred "
            f"{expected_quarter.label}; preferring document's stated period"
        )

    v.matches_expected = kind_ok
    # 'ok' only when the kind matches and nothing contradicts the period.
    v.status = "ok" if (kind_ok and period_ok) else "unverified"
    return v
