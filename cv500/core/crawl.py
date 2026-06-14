"""crawl.py — a polite HTTP fetcher.

Honours the cross-cutting crawler rules (Sections 2.5, 2.6, 2.7):
  * respect robots.txt
  * descriptive User-Agent
  * rate-limit to ~1-2 requests/sec per host
  * timeouts + a couple of retries with exponential backoff
  * do NOT solve CAPTCHAs or bypass bot-detection / login walls — if blocked, log it,
    return a 'blocked' result, and let the caller mark the item MISSING/NEEDS-DATA
  * never fetch a US source (SEC / EDGAR) — guarded explicitly

Every fetch returns a FetchResult (it never raises on network failure) so callers
can fail per-item and keep going. The Playwright fallback is optional: if the package
is not installed, render() returns a result whose reason explains that, and the
caller degrades to MISSING.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Dict, Optional

import requests

from .. import specs
from .provenance import Provenance, stamp

# Reasons mirror the MISSING vocabulary so callers can pass them straight through.
REASON_OK = "ok"
REASON_BLOCKED = "blocked"          # 401/403/429/captcha/login wall
REASON_NOT_FOUND = "not found"      # 404 / 410
REASON_SITE_ERROR = "site error"    # timeouts, 5xx, connection errors
REASON_FORBIDDEN = "forbidden"      # a disallowed (e.g. US) host — we refuse to fetch
REASON_ROBOTS = "robots-disallow"   # robots.txt forbids this path
REASON_NO_PLAYWRIGHT = "playwright-not-installed"


@dataclass
class FetchResult:
    ok: bool
    url: str
    final_url: str = ""
    status: Optional[int] = None
    reason: str = REASON_OK
    content: Optional[bytes] = None
    text: Optional[str] = None
    provenance: Optional[Provenance] = None
    error: str = ""

    @property
    def missing_reason(self) -> str:
        """Map an internal reason to the MISSING-section vocabulary."""
        if self.reason in (REASON_BLOCKED, REASON_ROBOTS):
            return "blocked"
        if self.reason == REASON_NOT_FOUND:
            return "not found"
        return "site error"


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def is_forbidden_host(url: str) -> bool:
    """True if the URL points at a source we must never fetch (US sources)."""
    host = _host(url)
    return any(bad in host for bad in specs.FORBIDDEN_HOST_SUBSTRINGS)


class Crawler:
    """A single polite fetcher. Reuse one instance for a whole run so rate-limiting
    and robots caches are shared across requests to the same host."""

    def __init__(self,
                 user_agent: str = specs.CRAWL_USER_AGENT,
                 min_interval: float = specs.CRAWL_MIN_INTERVAL_SEC,
                 timeout: int = specs.CRAWL_TIMEOUT_SEC,
                 max_retries: int = specs.CRAWL_MAX_RETRIES,
                 backoff_base: float = specs.CRAWL_BACKOFF_BASE_SEC,
                 respect_robots: bool = True,
                 verbose: bool = True) -> None:
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.respect_robots = respect_robots
        self.verbose = verbose

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
            "Accept-Language": "en-IN,en;q=0.9",
        })
        self._last_request: Dict[str, float] = {}
        self._robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    # -- politeness helpers --------------------------------------------------

    def _throttle(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            wait = self.min_interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def _robots_for(self, url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        host = _host(url)
        if host in self._robots:
            return self._robots[host]
        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            # Fetch robots ourselves so it respects our timeout and UA.
            resp = self.session.get(robots_url, timeout=self.timeout)
            if resp.status_code >= 400:
                rp = None  # no usable robots -> default allow (standard behaviour)
            else:
                rp.parse(resp.text.splitlines())
        except requests.RequestException:
            rp = None
        self._robots[host] = rp
        return rp

    def can_fetch(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = self._robots_for(url)
        if rp is None:
            return True  # no robots.txt readable -> allowed
        return rp.can_fetch(self.user_agent, url)

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # -- core fetch ----------------------------------------------------------

    def fetch(self, url: str, *, want_binary: bool = False,
              source_site: str = "company") -> FetchResult:
        """Fetch a URL politely. Always returns a FetchResult; never raises for
        network problems."""
        if is_forbidden_host(url):
            self._log(f"  [REFUSE] forbidden (US) source, not fetching: {url}")
            return FetchResult(ok=False, url=url, reason=REASON_FORBIDDEN,
                               error="US source is out of scope")

        if not self.can_fetch(url):
            self._log(f"  [robots] disallowed by robots.txt: {url}")
            return FetchResult(ok=False, url=url, reason=REASON_ROBOTS,
                               error="disallowed by robots.txt")

        host = _host(url)
        attempt = 0
        while True:
            self._throttle(host)
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            except requests.Timeout:
                if attempt < self.max_retries:
                    self._backoff(attempt); attempt += 1; continue
                return FetchResult(ok=False, url=url, reason=REASON_SITE_ERROR,
                                   error="timeout")
            except requests.RequestException as exc:
                if attempt < self.max_retries:
                    self._backoff(attempt); attempt += 1; continue
                return FetchResult(ok=False, url=url, reason=REASON_SITE_ERROR,
                                   error=f"{type(exc).__name__}: {exc}")

            status = resp.status_code
            prov = stamp(url, source_site=source_site, http_status=status)

            if status in (401, 403, 429):
                # Blocked / bot-detected. Do NOT try to bypass. One gentle retry on 429.
                if status == 429 and attempt < self.max_retries:
                    self._backoff(attempt); attempt += 1; continue
                self._log(f"  [blocked] HTTP {status}: {url}")
                return FetchResult(ok=False, url=url, final_url=resp.url, status=status,
                                   reason=REASON_BLOCKED, provenance=prov,
                                   error=f"HTTP {status}")
            if status in (404, 410):
                return FetchResult(ok=False, url=url, final_url=resp.url, status=status,
                                   reason=REASON_NOT_FOUND, provenance=prov,
                                   error=f"HTTP {status}")
            if status >= 500:
                if attempt < self.max_retries:
                    self._backoff(attempt); attempt += 1; continue
                return FetchResult(ok=False, url=url, final_url=resp.url, status=status,
                                   reason=REASON_SITE_ERROR, provenance=prov,
                                   error=f"HTTP {status}")
            if status >= 400:
                return FetchResult(ok=False, url=url, final_url=resp.url, status=status,
                                   reason=REASON_SITE_ERROR, provenance=prov,
                                   error=f"HTTP {status}")

            # 2xx/3xx-resolved success.
            result = FetchResult(ok=True, url=url, final_url=resp.url, status=status,
                                 reason=REASON_OK, provenance=prov)
            if want_binary:
                result.content = resp.content
            else:
                # Let requests decode text; fall back to utf-8.
                result.text = resp.text
                result.content = resp.content
            return result

    def _backoff(self, attempt: int) -> None:
        delay = self.backoff_base * (2 ** attempt)
        self._log(f"  [retry] backing off {delay:.1f}s ...")
        time.sleep(delay)

    # -- optional JS rendering ----------------------------------------------

    def render(self, url: str, *, wait_ms: int = 2500) -> FetchResult:
        """Render a JavaScript-heavy page with Playwright (Chromium), if available.

        Returns a FetchResult with .text set to the rendered HTML. If Playwright is
        not installed, returns ok=False reason=playwright-not-installed so the caller
        can degrade to MISSING rather than crash.
        """
        if is_forbidden_host(url):
            return FetchResult(ok=False, url=url, reason=REASON_FORBIDDEN,
                               error="US source is out of scope")
        if not self.can_fetch(url):
            return FetchResult(ok=False, url=url, reason=REASON_ROBOTS,
                               error="disallowed by robots.txt")
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception:
            return FetchResult(ok=False, url=url, reason=REASON_NO_PLAYWRIGHT,
                               error="playwright not installed (pip install playwright "
                                     "&& playwright install chromium)")
        try:
            self._throttle(_host(url))
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=self.user_agent)
                page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(wait_ms)
                html = page.content()
                browser.close()
            return FetchResult(ok=True, url=url, final_url=url, status=200,
                               reason=REASON_OK, text=html,
                               provenance=stamp(url, http_status=200,
                                                note="rendered with Playwright"))
        except Exception as exc:  # noqa: BLE001 - degrade gracefully on any render error
            return FetchResult(ok=False, url=url, reason=REASON_SITE_ERROR,
                               error=f"playwright render failed: {type(exc).__name__}: {exc}")
