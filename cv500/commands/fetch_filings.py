"""fetch-filings — PHASE 1 PRIORITY (Section 6.1).

Given a company's main website URL, find and download the latest N fiscal years
(default 5) of annual reports plus the earnings-call (concall) transcripts for those
same N fiscal years, and package them into one zip named after the company.

Strategy (layered; stop as soon as the N-year grid is full):
  1. Discover the investor-relations entry point from the homepage.
  2. From there, crawl the annual-reports and concall/quarterly sections (bounded BFS,
     following pagination / archive links), collecting candidate PDF links with their
     visible text and nearby context.
  3. Infer the latest N fiscal years from what actually EXISTS (anchor on the most
     recent AR found), not from the calendar.
  4. For each grid cell, download the best candidate, validate it is the right
     document and fiscal year, dedup, and keep it.
  5. Indian-market fallback: if the grid is still incomplete and a ticker is known,
     fill gaps from screener.in (which links to BSE/NSE-hosted PDFs).

Everything degrades per-item: a blocked page or missing file only affects that cell;
the run completes and reports the gap in the MISSING section.
"""

from __future__ import annotations

import hashlib
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .. import specs
from ..core import naming
from ..core.crawl import Crawler, FetchResult
from ..core.fiscal import (QuarterRef, fy_label, latest_n_fiscal_years,
                           parse_fiscal_year, parse_quarter, quarter_label)
from ..core.manifest import ManifestEntry, write_manifest_file
from ..core.needsdata import MissingItem
from ..core import pdfval

# --- discovery tuning -------------------------------------------------------
MAX_PAGES = 40          # bounded crawl: total HTML pages fetched from the company site
MAX_DEPTH = 3           # link depth from the homepage
MAX_DOWNLOAD_ATTEMPTS_PER_SLOT = 3

# Keywords that mark a link as leading toward investor-relations / documents.
_IR_KEYWORDS = (
    "investor", "investors", "investor-relations", "investor relations",
    "financials", "financial-reports", "financial reports", "annual-report",
    "annual report", "annualreport", "reports", "shareholder", "disclosures",
    "quarterly", "results", "presentations", "concall", "con-call", "transcript",
    "earnings", "filing", "filings", "archive", "older",
)
# Keywords that mark a link as an annual report.
_AR_HINTS = ("annual report", "annual-report", "annualreport", "ar-", "ar_",
             "annual_report", "integrated report", "integrated-report")
# Keywords that mark a link as a concall transcript (NOT audio / NOT a presentation).
_TRANSCRIPT_HINTS = ("transcript", "concall", "con-call", "conference call",
                     "conference-call", "earnings call", "earnings-call")


@dataclass
class Candidate:
    url: str
    link_text: str
    context: str
    source_site: str = "company"
    doc_type: str = "unknown"             # 'AR' | 'concall' | 'unknown'
    fiscal_year: Optional[int] = None
    quarter: Optional[QuarterRef] = None

    @property
    def blob(self) -> str:
        return f"{self.link_text}  {self.context}  {self.url}".lower()


# --- helpers ----------------------------------------------------------------

def _registered_domain(host: str) -> str:
    parts = host.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


def _same_site(url_a: str, url_b: str) -> bool:
    return _registered_domain(urlparse(url_a).netloc) == _registered_domain(urlparse(url_b).netloc)


def _is_pdf_link(href: str) -> bool:
    path = urlparse(href).path.lower()
    return path.endswith(".pdf")


def _looks_like_ir(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in _IR_KEYWORDS)


def _link_context(a_tag) -> str:
    """Gather nearby text (title attr + enclosing row/list item) to help detect the
    year/quarter when the link text itself is just 'Download' / 'PDF'."""
    parts: List[str] = []
    title = a_tag.get("title")
    if title:
        parts.append(title)
    parent = a_tag.find_parent(["tr", "td", "li", "p", "h1", "h2", "h3", "h4", "div"])
    if parent is not None:
        parts.append(parent.get_text(" ", strip=True)[:240])
    return " | ".join(parts)


def classify(c: Candidate) -> None:
    """Set doc_type, fiscal_year and quarter on a candidate from its text/url."""
    blob = c.blob
    q = parse_quarter(c.link_text) or parse_quarter(c.context) or parse_quarter(c.url)
    fy = parse_fiscal_year(c.link_text) or parse_fiscal_year(c.context) or parse_fiscal_year(c.url)

    is_transcript = any(h in blob for h in _TRANSCRIPT_HINTS)
    is_ar = any(h in blob for h in _AR_HINTS)

    if is_transcript and q is not None:
        c.doc_type = "concall"
        c.quarter = q
        c.fiscal_year = q.fiscal_year
    elif is_ar:
        c.doc_type = "AR"
        c.fiscal_year = fy
    elif is_transcript:
        # transcript without a clean quarter — keep but mark; year if any
        c.doc_type = "concall"
        c.quarter = q
        c.fiscal_year = (q.fiscal_year if q else fy)
    else:
        c.doc_type = "unknown"
        c.fiscal_year = fy
        c.quarter = q


def _ar_score(c: Candidate) -> int:
    s = 0
    b = c.blob
    if any(h in b for h in _AR_HINTS):
        s += 5
    if c.source_site == "company":
        s += 2
    if "xbrl" in b or "notice" in b or "agm" in b:
        s -= 3   # AGM notices / XBRL are not the report itself
    return s


def _concall_score(c: Candidate) -> int:
    s = 0
    b = c.blob
    if "transcript" in b:
        s += 6       # strongly prefer the transcript over audio/ppt
    if any(h in b for h in ("concall", "conference call", "earnings call")):
        s += 3
    if c.source_site == "company":
        s += 2
    if "audio" in b or "recording" in b or ".mp3" in b:
        s -= 5
    if "presentation" in b or "ppt" in b or "investor presentation" in b:
        s -= 4
    return s


# --- discovery (bounded BFS over the company site) --------------------------

def discover_candidates(crawler: Crawler, start_url: str) -> List[Candidate]:
    """Bounded BFS from the homepage, collecting PDF candidates and following only
    IR/document links on the same registered domain."""
    visited: set = set()
    frontier: List[Tuple[str, int]] = [(start_url, 0)]
    candidates: List[Candidate] = []
    seen_pdf: set = set()
    pages = 0

    while frontier and pages < MAX_PAGES:
        url, depth = frontier.pop(0)
        norm = url.split("#")[0]
        if norm in visited:
            continue
        visited.add(norm)

        res = crawler.fetch(url, source_site="company")
        pages += 1
        html = res.text if res.ok else None

        # If the page returned little/no parseable HTML, try a JS render once.
        if (not html) and res.ok is False and res.reason in ("site error",):
            pass  # leave; counted as a failed page
        if html is None:
            print(f"  [skip] {res.reason}: {url}")
            continue

        soup = BeautifulSoup(html, "lxml")

        # Heuristic: if a page has almost no links/text, it may be JS-rendered.
        anchors = soup.find_all("a", href=True)
        if len(anchors) < 5 and depth == 0:
            rendered = crawler.render(url)
            if rendered.ok and rendered.text:
                soup = BeautifulSoup(rendered.text, "lxml")
                anchors = soup.find_all("a", href=True)
                print(f"  [render] used Playwright for {url} ({len(anchors)} links)")

        for a in anchors:
            href = a.get("href", "").strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            absu = urljoin(res.final_url or url, href)
            if not absu.lower().startswith(("http://", "https://")):
                continue
            link_text = a.get_text(" ", strip=True)

            if _is_pdf_link(absu):
                if absu in seen_pdf:
                    continue
                seen_pdf.add(absu)
                candidates.append(Candidate(
                    url=absu, link_text=link_text, context=_link_context(a),
                    source_site="company"))
                continue

            # Follow deeper only on-site, within depth, and only IR/doc-ish links.
            if depth < MAX_DEPTH and _same_site(start_url, absu):
                if _looks_like_ir(link_text) or _looks_like_ir(href):
                    nxt = absu.split("#")[0]
                    if nxt not in visited:
                        frontier.append((absu, depth + 1))

    print(f"  discovered {len(candidates)} PDF candidate link(s) across {pages} page(s)")
    return candidates


def discover_screener(crawler: Crawler, ticker: str) -> List[Candidate]:
    """Best-effort Indian-market fallback: parse screener.in's documents section,
    which lists annual reports and concall transcripts (links to BSE/NSE PDFs)."""
    out: List[Candidate] = []
    url = f"https://www.screener.in/company/{ticker}/"
    res = crawler.fetch(url, source_site="screener")
    if not res.ok or not res.text:
        consolidated = f"https://www.screener.in/company/{ticker}/consolidated/"
        res = crawler.fetch(consolidated, source_site="screener")
    if not res.ok or not res.text:
        print(f"  [screener] could not load documents for {ticker}: {res.reason}")
        return out
    soup = BeautifulSoup(res.text, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        absu = urljoin(res.final_url or url, href)
        if not absu.lower().startswith("http"):
            continue
        blob = f"{text} {href}".lower()
        if _is_pdf_link(absu) or "transcript" in blob or "annual report" in blob:
            out.append(Candidate(url=absu, link_text=text,
                                 context="screener documents", source_site="screener"))
    print(f"  [screener] found {len(out)} candidate link(s) for {ticker}")
    return out


# --- main run ---------------------------------------------------------------

def _detect_company_name(crawler: Crawler, homepage: FetchResult,
                         override: Optional[str], ticker: Optional[str]) -> str:
    if override:
        return naming.clean_company_name(override)
    title = None
    if homepage.ok and homepage.text:
        soup = BeautifulSoup(homepage.text, "lxml")
        if soup.title and soup.title.string:
            title = soup.title.string
        if not title:
            og = soup.find("meta", attrs={"property": "og:site_name"})
            if og and og.get("content"):
                title = og["content"]
    if title:
        # Titles are often "Home | Marico Limited" or "Marico - Leading FMCG".
        cleaned = re.split(r"[|\-–—:]", title)[0]
        if len(cleaned.strip()) < 3 and "|" in title:
            cleaned = re.split(r"[|]", title)[1]
        name = naming.clean_company_name(cleaned)
        if name and name != "COMPANY":
            return name
    if ticker:
        return naming.clean_company_name(ticker)
    return "COMPANY"


def run(args) -> int:
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    years = args.years
    crawler = Crawler(verbose=True)

    print(f"== fetch-filings ==")
    print(f"  url={args.url}  years={years}  out={out_dir}")

    # 1) homepage + company name
    home = crawler.fetch(args.url, source_site="company")
    if not home.ok:
        print(f"  [warn] homepage fetch failed ({home.reason}); will rely on fallback if --ticker given")
    name = _detect_company_name(crawler, home, args.name, args.ticker)
    print(f"  company name token: {name}")

    # 2) discover candidates from the company site
    candidates: List[Candidate] = []
    if home.ok:
        candidates.extend(discover_candidates(crawler, home.final_url or args.url))

    for c in candidates:
        classify(c)

    # 3) anchor on the most recent AR fiscal year that actually exists
    ar_years = sorted({c.fiscal_year for c in candidates
                       if c.doc_type == "AR" and c.fiscal_year}, reverse=True)
    all_years = sorted({c.fiscal_year for c in candidates if c.fiscal_year}, reverse=True)
    anchor = ar_years[0] if ar_years else (all_years[0] if all_years else None)

    if anchor is None and args.ticker:
        # Nothing from the site; try screener purely to anchor.
        candidates.extend(discover_screener(crawler, args.ticker))
        for c in candidates:
            classify(c)
        ar_years = sorted({c.fiscal_year for c in candidates
                           if c.doc_type == "AR" and c.fiscal_year}, reverse=True)
        anchor = ar_years[0] if ar_years else None

    if anchor is None:
        print("  [NEEDS-DATA] could not find any dated annual report to anchor the "
              "fiscal-year grid. Nothing downloaded.")
        # Still emit an empty manifest naming the whole grid as missing.
        return _finalize(out_dir, name, years, [], _empty_grid_missing(years, reason="not found"))

    target_years = latest_n_fiscal_years(anchor, years)
    print(f"  anchor FY = {fy_label(anchor)};  target years = "
          f"{', '.join(fy_label(y) for y in target_years)}")

    # 4) build needed slots and fill them
    kept: List[ManifestEntry] = []
    missing: List[MissingItem] = []
    content_hashes: set = set()
    work_files: Dict[str, bytes] = {}   # zip-internal path -> bytes

    # Group candidates for quick lookup.
    ar_by_year: Dict[int, List[Candidate]] = {}
    cc_by_slot: Dict[Tuple[int, int], List[Candidate]] = {}
    for c in candidates:
        if c.doc_type == "AR" and c.fiscal_year:
            ar_by_year.setdefault(c.fiscal_year, []).append(c)
        elif c.doc_type == "concall" and c.quarter:
            cc_by_slot.setdefault((c.quarter.fiscal_year, c.quarter.quarter), []).append(c)

    screener_tried = False

    def ensure_screener():
        nonlocal screener_tried, candidates, ar_by_year, cc_by_slot
        if screener_tried or not args.ticker:
            return
        screener_tried = True
        extra = discover_screener(crawler, args.ticker)
        for c in extra:
            classify(c)
            if c.doc_type == "AR" and c.fiscal_year:
                ar_by_year.setdefault(c.fiscal_year, []).append(c)
            elif c.doc_type == "concall" and c.quarter:
                cc_by_slot.setdefault((c.quarter.fiscal_year, c.quarter.quarter), []).append(c)

    # 4a) annual reports
    for fy in target_years:
        slot_name = f"Annual Report {fy_label(fy)}"
        cands = sorted(ar_by_year.get(fy, []), key=_ar_score, reverse=True)
        if not cands:
            ensure_screener()
            cands = sorted(ar_by_year.get(fy, []), key=_ar_score, reverse=True)
        entry, reason = _fill_slot(
            crawler, cands, expected_kind=pdfval.KIND_AR, expected_fy=fy,
            expected_q=None, name=name, content_hashes=content_hashes,
            work_files=work_files, zip_subdir="Annual_Reports",
            out_filename=naming.ar_filename(name, fy), fy_label_str=fy_label(fy),
            quarter_label_str="")
        if entry:
            kept.append(entry)
            print(f"  [ok] {slot_name} -> {entry.filename} ({entry.validation_status})")
        else:
            missing.append(MissingItem(item=slot_name, reason=reason,
                                       detail="no validating candidate found"))
            print(f"  [MISSING] {slot_name}: {reason}")

    # 4b) concall transcripts (up to 4 quarters per year)
    for fy in target_years:
        for q in (1, 2, 3, 4):
            qref = QuarterRef(fiscal_year=fy, quarter=q)
            slot_name = f"Transcript {quarter_label(q)} {fy_label(fy)}"
            cands = sorted(cc_by_slot.get((fy, q), []), key=_concall_score, reverse=True)
            if not cands:
                ensure_screener()
                cands = sorted(cc_by_slot.get((fy, q), []), key=_concall_score, reverse=True)
            if not cands:
                missing.append(MissingItem(item=slot_name, reason="not found",
                                           detail="no transcript candidate located"))
                continue
            entry, reason = _fill_slot(
                crawler, cands, expected_kind=pdfval.KIND_TRANSCRIPT, expected_fy=fy,
                expected_q=qref, name=name, content_hashes=content_hashes,
                work_files=work_files, zip_subdir="Earnings_Call_Transcripts",
                out_filename=naming.concall_filename(name, qref),
                fy_label_str=fy_label(fy), quarter_label_str=quarter_label(q))
            if entry:
                kept.append(entry)
                print(f"  [ok] {slot_name} -> {entry.filename} ({entry.validation_status})")
            else:
                missing.append(MissingItem(item=slot_name, reason=reason,
                                           detail="no validating candidate found"))
                print(f"  [MISSING] {slot_name}: {reason}")

    return _finalize(out_dir, name, years, kept, missing, work_files)


def _fill_slot(crawler, cands, *, expected_kind, expected_fy, expected_q, name,
               content_hashes, work_files, zip_subdir, out_filename,
               fy_label_str, quarter_label_str) -> Tuple[Optional[ManifestEntry], str]:
    """Try candidates for one grid slot in preference order; download, validate,
    dedup. Returns (entry, '') on success or (None, reason) on failure."""
    reason = "not found"
    for c in cands[:MAX_DOWNLOAD_ATTEMPTS_PER_SLOT]:
        res = crawler.fetch(c.url, want_binary=True, source_site=c.source_site)
        if not res.ok or not res.content:
            reason = res.missing_reason if res else "site error"
            continue
        digest = hashlib.sha256(res.content).hexdigest()
        if digest in content_hashes:
            # exact duplicate of a file already kept; treat slot as satisfied-elsewhere
            continue
        v = pdfval.validate(res.content, expected_kind=expected_kind,
                            expected_fiscal_year=expected_fy,
                            expected_quarter=expected_q)
        if not v.is_pdf:
            reason = "site error"
            continue
        # Reject only if it clearly is the OTHER kind of document.
        wrong_kind = (v.kind != pdfval.KIND_UNKNOWN and v.kind != expected_kind)
        if wrong_kind:
            reason = "not found"
            continue
        content_hashes.add(digest)
        zip_path = f"{zip_subdir}/{out_filename}"
        work_files[zip_path] = res.content
        prov = res.provenance
        return (ManifestEntry(
            document_type=expected_kind,
            fiscal_year=fy_label_str,
            quarter=quarter_label_str,
            filename=out_filename,
            source_url=c.url,
            source_site=c.source_site,
            retrieval_datetime=prov.retrieval_datetime if prov else "",
            validation_status=v.status,
        ), "")
    return (None, reason)


def _empty_grid_missing(years: int, reason: str) -> List[MissingItem]:
    items: List[MissingItem] = []
    # We cannot know the actual fiscal years without an anchor, so name the grid shape.
    for i in range(years):
        items.append(MissingItem(item=f"Annual Report (year -{i})", reason=reason,
                                  detail="no anchor fiscal year could be established"))
    return items


def _finalize(out_dir: str, name: str, years: int, kept: List[ManifestEntry],
              missing: List[MissingItem], work_files: Optional[Dict[str, bytes]] = None) -> int:
    zip_filename = naming.zip_name(name, years)
    zip_path = os.path.join(out_dir, zip_filename)
    manifest_path = os.path.join(out_dir, f"{name}_manifest.csv")

    write_manifest_file(manifest_path, kept, missing)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in (work_files or {}).items():
            zf.writestr(arcname, data)
        # also embed the manifest inside the zip
        with open(manifest_path, "rb") as mf:
            zf.writestr("_manifest.csv", mf.read())

    print("\n== summary ==")
    print(f"  kept {len(kept)} document(s); {len(missing)} grid cell(s) MISSING")
    print(f"  zip:      {zip_path}")
    print(f"  manifest: {manifest_path}")
    # A short, honest result always beats a padded one.
    return 0
