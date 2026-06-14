"""screen-ingest — the screen-day front door (Section 6.7).

Dedups the lane export CSVs, flags dual-lane hits as a conviction modifier, and
cross-references each hit against the graveyard_log and park_list to TAG it. It does
NOT re-run any screen; it is file-driven and fully deterministic.

Tags (Section 6.7):
  new                            -> into the kill sweep (never seen)
  parked-trigger-fired           -> promote to a fresh study
  parked-trigger-not-met         -> stays parked (noted)
  parked-trigger-check-needs-data-> trigger needs current data that isn't available
  graveyarded-structural         -> suppress; show prior reason/date; do not re-study
  graveyarded-revisitable        -> surface prior reasoning for a joint human decision

Output: a deduped, tagged hit list CSV + a short console summary.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..core import naming
from ..core.needsdata import Result, passed, flag, needs_data
from ..core.report import print_results

TAG_NEW = "new"
TAG_PARK_FIRED = "parked-trigger-fired"
TAG_PARK_NOT_MET = "parked-trigger-not-met"
TAG_PARK_NEEDS_DATA = "parked-trigger-check-needs-data"
TAG_GRAVE_STRUCTURAL = "graveyarded-structural"
TAG_GRAVE_REVISITABLE = "graveyarded-revisitable"

_RULE = "Section 6.7 (screen-day dedup + memory cross-reference)"


# --- flexible CSV identity reading ------------------------------------------

def _find_col(fieldnames, *names) -> Optional[str]:
    low = {(c or "").strip().lower(): c for c in (fieldnames or [])}
    for n in names:
        if n in low:
            return low[n]
    return None


def _identity(row: dict, cols: dict) -> Tuple[str, str, str]:
    company = (row.get(cols.get("company", "")) or "").strip()
    ticker = (row.get(cols.get("ticker", "")) or "").strip()
    isin = (row.get(cols.get("isin", "")) or "").strip()
    return company, ticker, isin


def _key(company: str, ticker: str, isin: str) -> str:
    """Dedup key: prefer ISIN, then ticker, then a cleaned company name."""
    if isin:
        return f"isin:{isin.upper()}"
    if ticker:
        return f"tk:{ticker.upper()}"
    return f"nm:{naming.clean_company_name(company)}"


def _lane_from_filename(path: str) -> str:
    base = os.path.basename(path)
    m = re.search(r"CV500[-_ ]?([A-F]2?|B2)", base, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"[-_ ]([A-F]2?)\.csv$", base, re.IGNORECASE)
    return m.group(1).upper() if m else os.path.splitext(base)[0]


@dataclass
class Hit:
    key: str
    company: str = ""
    ticker: str = ""
    isin: str = ""
    lanes: List[str] = field(default_factory=list)
    tag: str = TAG_NEW
    note: str = ""

    @property
    def dual_lane(self) -> bool:
        return len(set(self.lanes)) >= 2


def _load_lane(path: str) -> Tuple[List[Tuple[str, str, str]], str, Optional[str]]:
    """Return (rows, lane_label, error). error is None on success."""
    rows: List[Tuple[str, str, str]] = []
    lane = _lane_from_filename(path)
    if not os.path.exists(path):
        return rows, lane, f"lane CSV not found: {path}"
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = {
            "company": _find_col(reader.fieldnames, "company", "name", "company name"),
            "ticker": _find_col(reader.fieldnames, "ticker", "symbol", "nse symbol", "bse code"),
            "isin": _find_col(reader.fieldnames, "isin"),
        }
        if not any(cols.values()):
            return rows, lane, f"{path}: no company/ticker/isin column found"
        for row in reader:
            company, ticker, isin = _identity(row, cols)
            if company or ticker or isin:
                rows.append((company, ticker, isin))
    return rows, lane, None


def _load_memory(path: str, kind: str) -> Tuple[Dict[str, dict], Optional[str]]:
    """Load graveyard_log or park_list into {key: row}. kind in {'graveyard','park'}."""
    out: Dict[str, dict] = {}
    if not path:
        return out, None
    if not os.path.exists(path):
        return out, f"{kind} file not found: {path}"
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = {
            "company": _find_col(reader.fieldnames, "company", "name"),
            "ticker": _find_col(reader.fieldnames, "ticker", "symbol"),
            "isin": _find_col(reader.fieldnames, "isin"),
        }
        for row in reader:
            company, ticker, isin = _identity(row, cols)
            k = _key(company, ticker, isin)
            out[k] = {kk.strip().lower(): (vv or "").strip()
                      for kk, vv in row.items() if kk}
    return out, None


def _classify_park(row: dict) -> str:
    status = (row.get("trigger_status", "") or "").strip().lower()
    if not status or status in ("unknown", "n/a", "na", "needs-data", "needs data",
                                "pending-data", "tbd", "?"):
        return TAG_PARK_NEEDS_DATA
    if any(w in status for w in ("fired", "met", "true", "yes", "triggered", "hit")):
        # guard against "not met"
        if "not" in status:
            return TAG_PARK_NOT_MET
        return TAG_PARK_FIRED
    if any(w in status for w in ("not met", "not-met", "no", "false", "unmet", "pending")):
        return TAG_PARK_NOT_MET
    return TAG_PARK_NEEDS_DATA


def run(args) -> int:
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    results: List[Result] = []

    if not args.lane_csv:
        results.append(needs_data("lane exports",
                                  "no lane export CSVs supplied (--lane-csv A.csv ...)",
                                  rule=_RULE))
        print_results("screen-ingest", results)
        return 0

    # 1) load + dedup lanes
    hits: Dict[str, Hit] = {}
    for path in args.lane_csv:
        rows, lane, lerr = _load_lane(path)
        if lerr:
            results.append(needs_data("lane file", lerr, rule=_RULE))
            continue
        for company, ticker, isin in rows:
            k = _key(company, ticker, isin)
            h = hits.get(k)
            if h is None:
                h = Hit(key=k, company=company, ticker=ticker, isin=isin)
                hits[k] = h
            h.lanes.append(lane)
            # backfill identity if a later lane has more complete fields
            h.company = h.company or company
            h.ticker = h.ticker or ticker
            h.isin = h.isin or isin

    # 2) load memory
    graveyard, gerr = _load_memory(args.graveyard, "graveyard")
    park, perr = _load_memory(args.park_list, "park")
    if gerr:
        results.append(needs_data("graveyard_log", gerr, rule=_RULE))
    if perr:
        results.append(needs_data("park_list", perr, rule=_RULE))

    # 3) cross-reference + tag (graveyard precedence over park)
    for h in hits.values():
        grow = graveyard.get(h.key)
        prow = park.get(h.key)
        if grow is not None:
            disp = (grow.get("disposition", "") or "").strip().lower()
            when = grow.get("date", "")
            reason = grow.get("reason", "") or grow.get("kill_condition", "")
            if disp == "structural":
                h.tag = TAG_GRAVE_STRUCTURAL
                h.note = f"prior structural kill {when}: {reason}".strip()
            elif disp == "revisitable":
                h.tag = TAG_GRAVE_REVISITABLE
                h.note = f"prior revisitable kill {when}: {reason}".strip()
            else:
                # graveyarded but disposition unclear -> surface for human, needs data
                h.tag = TAG_GRAVE_REVISITABLE
                h.note = (f"prior kill {when}: {reason}; disposition unspecified "
                          f"-> treat as revisitable, confirm").strip()
        elif prow is not None:
            h.tag = _classify_park(prow)
            trig = prow.get("re_screen_trigger", "")
            stat = prow.get("trigger_status", "")
            h.note = f"trigger: {trig} | status: {stat}".strip(" |")
        else:
            h.tag = TAG_NEW

    # 4) write tagged hit list CSV
    out_csv = os.path.join(out_dir, "screen_ingest_hits.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["company", "ticker", "isin", "lanes", "dual_lane", "tag", "note"])
        for h in sorted(hits.values(), key=lambda z: (z.tag, z.company)):
            w.writerow([h.company, h.ticker, h.isin, "+".join(sorted(set(h.lanes))),
                        "yes" if h.dual_lane else "", h.tag, h.note])

    # 5) console summary as Results
    by_tag: Dict[str, int] = {}
    dual = 0
    for h in hits.values():
        by_tag[h.tag] = by_tag.get(h.tag, 0) + 1
        if h.dual_lane:
            dual += 1

    for tag in (TAG_NEW, TAG_PARK_FIRED, TAG_PARK_NOT_MET, TAG_PARK_NEEDS_DATA,
                TAG_GRAVE_STRUCTURAL, TAG_GRAVE_REVISITABLE):
        n = by_tag.get(tag, 0)
        if n == 0:
            continue
        if tag in (TAG_NEW, TAG_PARK_FIRED):
            results.append(passed(f"{tag}", f"{n} hit(s)", rule=_RULE))
        elif tag == TAG_PARK_NEEDS_DATA:
            results.append(needs_data(f"{tag}", f"{n} parked hit(s) whose trigger needs "
                                      f"current data to evaluate", rule=_RULE))
        else:
            results.append(flag(f"{tag}", f"{n} hit(s)", rule=_RULE))

    if dual:
        results.append(flag("dual-lane hits", f"{dual} name(s) hit in >=2 lanes "
                            "(conviction modifier)", rule=_RULE))

    print_results("screen-ingest", results)
    print(f"\n  deduped {sum(len(h.lanes) for h in hits.values())} lane rows -> "
          f"{len(hits)} unique names")
    print(f"  tagged hit list: {out_csv}")
    return 0
