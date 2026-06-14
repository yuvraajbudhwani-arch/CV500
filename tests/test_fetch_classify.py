"""Regression tests for fetch-filings candidate classification (Section 6.1).

These lock in the fixes for real false positives seen on a live IR site:
  * a regulatory "intimation order" whose URL contained 'utt[ar-]pradesh' must NOT be
    classified as an annual report;
  * an audio-recording notice must NOT be classified as a transcript;
  * 'fy2025-26' must resolve to FY2026 (range-aware), not FY2025.
"""

import pytest

from cv500.commands.fetch_filings import Candidate, classify


def _c(url):
    c = Candidate(url="https://example.in/" + url, link_text="", context="")
    classify(c)
    return c


def test_intimation_order_is_not_an_annual_report():
    c = _c("se-intimation-order-nina-percept-uttar-pradesh-11-12-2025.pdf")
    assert c.doc_type != "AR"


def test_audio_recording_is_not_a_transcript():
    c = _c("se-intimation-audio-recording-q4fy26-earnings-call.pdf")
    assert c.doc_type != "concall"


@pytest.mark.parametrize("url,fy", [
    ("SE-Intimation-Annual-Report-2023.pdf", 2023),
    ("SE-Intimation-AGM-Notice-and-Annual-report-2022.pdf", 2022),
    ("annual-report-2024-25.pdf", 2025),
    ("Integrated-Annual-Report-FY2024.pdf", 2024),
])
def test_real_annual_reports_classified(url, fy):
    c = _c(url)
    assert c.doc_type == "AR"
    assert c.fiscal_year == fy


@pytest.mark.parametrize("url,fy,q", [
    ("se-intimation-transcript-of-earnings-call-q3fy26.pdf", 2026, 3),
    ("Pidilite-Industries-Limited-Q1FY23-Earnings-call.pdf", 2023, 1),
    ("transcript-q3-fy2025-26.pdf", 2026, 3),
])
def test_real_transcripts_classified(url, fy, q):
    c = _c(url)
    assert c.doc_type == "concall"
    assert c.quarter is not None
    assert (c.quarter.fiscal_year, c.quarter.quarter) == (fy, q)
