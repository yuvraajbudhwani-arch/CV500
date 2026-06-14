"""Tests for the crawler's safety guards (no network performed)."""

from cv500.core import crawl
from cv500.core.crawl import FetchResult


def test_forbidden_us_hosts_are_refused():
    # The toolkit must NEVER fetch SEC / EDGAR or any US source (spec Section 1).
    assert crawl.is_forbidden_host("https://www.sec.gov/cgi-bin/browse-edgar")
    assert crawl.is_forbidden_host("https://efts.sec.gov/LATEST/search-index")
    assert crawl.is_forbidden_host("https://company.edgar-online.com/x")


def test_indian_hosts_allowed():
    assert not crawl.is_forbidden_host("https://www.nseindia.com")
    assert not crawl.is_forbidden_host("https://www.bseindia.com")
    assert not crawl.is_forbidden_host("https://www.screener.in/company/MARICO/")
    assert not crawl.is_forbidden_host("https://www.pidilite.com")


def test_fetch_refuses_forbidden_without_network():
    c = crawl.Crawler(verbose=False)
    res = c.fetch("https://www.sec.gov/edgar/filing.pdf")
    assert res.ok is False
    assert res.reason == crawl.REASON_FORBIDDEN


def test_missing_reason_mapping():
    assert FetchResult(False, "u", reason=crawl.REASON_BLOCKED).missing_reason == "blocked"
    assert FetchResult(False, "u", reason=crawl.REASON_ROBOTS).missing_reason == "blocked"
    assert FetchResult(False, "u", reason=crawl.REASON_NOT_FOUND).missing_reason == "not found"
    assert FetchResult(False, "u", reason=crawl.REASON_SITE_ERROR).missing_reason == "site error"
