"""Tests for core/naming.py — company-name + file/zip naming (Section 6.1)."""

import pytest

from cv500.core import naming
from cv500.core.fiscal import QuarterRef


def test_required_example_exactly():
    # The spec fixes this exact mapping.
    name = naming.clean_company_name("abc ltd.")
    assert name == "ABC"
    assert naming.zip_name(name, 5) == "ABC_5yr_AR_EC-Transcripts.zip"


@pytest.mark.parametrize("raw,expected", [
    ("abc ltd.", "ABC"),
    ("Reliance Industries Limited", "RELIANCE_INDUSTRIES"),
    ("Pidilite Industries Ltd", "PIDILITE_INDUSTRIES"),
    ("3M India Limited", "3M_INDIA"),
    ("Marico Ltd", "MARICO"),
    ("Example Pvt Ltd", "EXAMPLE"),
    ("Some Company Private Limited", "SOME_COMPANY"),
    ("Acme Corporation", "ACME"),
])
def test_clean_company_name(raw, expected):
    assert naming.clean_company_name(raw) == expected


def test_fallback_on_empty():
    assert naming.clean_company_name("", fallback="COMPANY") == "COMPANY"
    assert naming.clean_company_name("Ltd", fallback="COMPANY") == "COMPANY"
    assert naming.clean_company_name(None) == "COMPANY"


def test_zip_name_uses_actual_count():
    assert naming.zip_name("ABC", 3) == "ABC_3yr_AR_EC-Transcripts.zip"
    assert naming.zip_name("ABC", 5) == "ABC_5yr_AR_EC-Transcripts.zip"


def test_ar_and_concall_filenames():
    assert naming.ar_filename("ABC", 2025) == "ABC_AR_FY2025.pdf"
    assert naming.concall_filename("ABC", QuarterRef(2025, 1)) == "ABC_Concall_Q1_FY2025.pdf"
    assert naming.concall_filename("ABC", QuarterRef(2024, 3)) == "ABC_Concall_Q3_FY2024.pdf"
