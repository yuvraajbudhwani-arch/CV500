"""monthly-scan — Part 08 monthly monitoring sweep across held names (Section 6.8).

Per held name, gather/flag:
  * pledge + SAST/insider filings (flag any promoter sale > 0.5%)
  * ASM / GSM check
  * rating actions incl. INC / withdrawal
  * new MCA charge filings
  * bulk / block deals
  * price-volume anomaly: price -20% in 10 sessions on >= 1.5x average delivery with
    no disclosure -> forced-investigation flag
  * news + peer-result calendar

Per-name verdict: clear / interrupt / NEEDS-DATA, with the triggering item + source.

Live filings/news sources are not wired (they block or need per-source hardening), so
those items return NEEDS-DATA naming the source — never an assumed "clear". The
price-volume anomaly IS computed deterministically when a per-ticker price CSV is
supplied via --price-dir (columns: date, close, delivered_qty or delivered_value).
"""

from __future__ import annotations

import csv
import os
from typing import List, Optional, Tuple

from .. import specs
from ..core.needsdata import Result, passed, flag, needs_data
from ..core.report import print_results, write_results_csv

_RULE = "Section 6.8 (Part 08 monthly monitoring)"

# Items whose live sources are not wired -> NEEDS-DATA (named), per name.
_DEFERRED_ITEMS = [
    ("pledge / SAST / insider filings", "BSE/NSE SAST + insider (flag promoter sale > "
     f"{specs.MONTHLY_PROMOTER_SALE_FLAG_PCT}%)"),
    ("ASM / GSM", "NSE/BSE surveillance lists"),
    ("rating actions (incl. INC/withdrawal)", "CRISIL/ICRA/CARE/India Ratings"),
    ("new MCA charge filings", "MCA charge index"),
    ("bulk / block deals", "NSE/BSE bulk & block deal feeds"),
    ("news + peer-result calendar", "news + peer earnings calendar"),
]


def _parse_tickers(arg: Optional[str]) -> List[str]:
    if not arg:
        return []
    if arg.startswith("@"):
        path = arg[1:]
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip()]
    return [t.strip() for t in arg.split(",") if t.strip()]


def _load_price_csv(path: str) -> Tuple[Optional[List[float]], Optional[List[float]], str]:
    """Return (closes, deliveries, note). deliveries may be None if no such column."""
    closes: List[float] = []
    delivs: List[float] = []
    has_deliv = False
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = {(c or "").strip().lower(): c for c in (reader.fieldnames or [])}
        close_col = next((fields[k] for k in fields if k in
                          ("close", "close_price", "ltp", "last")), None)
        deliv_col = next((fields[k] for k in fields if k in
                          ("delivered_qty", "delivery_qty", "deliverable_qty",
                           "delivered_value", "delivery_value", "delivered", "deliverable")), None)
        if close_col is None:
            return None, None, "price CSV needs a 'close' column"
        for row in reader:
            try:
                closes.append(float((row.get(close_col) or "").replace(",", "").strip()))
            except ValueError:
                continue
            if deliv_col is not None:
                try:
                    delivs.append(float((row.get(deliv_col) or "").replace(",", "").strip()))
                    has_deliv = True
                except ValueError:
                    delivs.append(0.0)
    return closes, (delivs if has_deliv else None), f"{len(closes)} sessions"


def _price_volume_anomaly(closes: List[float], delivs: Optional[List[float]]) -> Result:
    """Compute the Section 6.8 anomaly. Rows must be in chronological order."""
    n_sessions = specs.MONTHLY_PRICE_DROP_SESSIONS
    if len(closes) < n_sessions + 1:
        return needs_data("price-volume anomaly",
                          f"need at least {n_sessions + 1} sessions of close prices, "
                          f"have {len(closes)}", rule=_RULE)
    start = closes[-(n_sessions + 1)]
    end = closes[-1]
    if start <= 0:
        return needs_data("price-volume anomaly", "invalid start price (<=0)", rule=_RULE)
    drop_pct = (start - end) / start * 100.0
    price_trig = drop_pct >= specs.MONTHLY_PRICE_DROP_PCT

    if delivs is None or len(delivs) < len(closes):
        # Price leg only — cannot evaluate the delivery condition.
        if price_trig:
            return needs_data("price-volume anomaly",
                              f"price fell {drop_pct:.1f}% over {n_sessions} sessions "
                              f"(>= {specs.MONTHLY_PRICE_DROP_PCT}%), but delivery volume "
                              "not supplied to confirm the >= "
                              f"{specs.MONTHLY_DELIVERY_MULTIPLE}x leg", rule=_RULE)
        return passed("price-volume anomaly",
                      f"price moved {drop_pct:.1f}% over {n_sessions} sessions "
                      f"(< {specs.MONTHLY_PRICE_DROP_PCT}% threshold)", rule=_RULE)

    # Use mean of the recent window vs the long-run average delivery.
    window = delivs[-n_sessions:]
    win_avg = sum(window) / len(window)
    long_avg = sum(delivs) / len(delivs)
    deliv_mult = (win_avg / long_avg) if long_avg > 0 else 0.0
    deliv_trig = deliv_mult >= specs.MONTHLY_DELIVERY_MULTIPLE

    if price_trig and deliv_trig:
        return flag("price-volume anomaly",
                    f"price -{drop_pct:.1f}% over {n_sessions} sessions on "
                    f"{deliv_mult:.2f}x avg delivery -> FORCED-INVESTIGATION "
                    "(verify there was no disclosure)", rule=_RULE)
    if price_trig and not deliv_trig:
        return passed("price-volume anomaly",
                      f"price -{drop_pct:.1f}% but delivery only {deliv_mult:.2f}x avg "
                      f"(< {specs.MONTHLY_DELIVERY_MULTIPLE}x) — no forced-investigation",
                      rule=_RULE)
    return passed("price-volume anomaly",
                  f"price moved {drop_pct:.1f}% over {n_sessions} sessions "
                  f"(< {specs.MONTHLY_PRICE_DROP_PCT}%)", rule=_RULE)


def run(args) -> int:
    out_dir = os.path.abspath(args.out)
    tickers = _parse_tickers(args.tickers)
    if not tickers:
        r = [needs_data("tickers", "supply --tickers AAA,BBB or --tickers @file.txt",
                        rule=_RULE)]
        print_results("monthly-scan", r)
        return 0

    all_rows: List[Result] = []
    print(f"== monthly-scan ==  {len(tickers)} held name(s)")

    for tk in tickers:
        per: List[Result] = []
        # price-volume anomaly (computable if a CSV is provided)
        price_csv = None
        if args.price_dir:
            cand = os.path.join(args.price_dir, f"{tk}.csv")
            if os.path.exists(cand):
                price_csv = cand
        if price_csv:
            closes, delivs, note = _load_price_csv(price_csv)
            if closes is None:
                per.append(needs_data("price-volume anomaly", note, rule=_RULE))
            else:
                per.append(_price_volume_anomaly(closes, delivs))
        else:
            per.append(needs_data("price-volume anomaly",
                                  "no per-ticker price CSV supplied (--price-dir) to "
                                  "compute the -20%/10-session + 1.5x-delivery test",
                                  rule=_RULE))
        # deferred live-source items
        for item, src in _DEFERRED_ITEMS:
            per.append(needs_data(item, f"source not wired — verify at: {src}", rule=_RULE))

        # per-name verdict
        statuses = {r.status for r in per}
        verdict = ("interrupt" if "FLAG" in statuses or "KILL" in statuses
                   else ("NEEDS-DATA" if "NEEDS-DATA" in statuses else "clear"))
        print(f"\n  -- {tk}: {verdict} --")
        for r in per:
            r.name = f"{tk}: {r.name}"
            all_rows.append(r)
        print_results(tk, per)

    write_results_csv(os.path.join(out_dir, "monthly_scan_result.csv"), all_rows)
    print(f"\n  full result: {os.path.join(out_dir, 'monthly_scan_result.csv')}")
    return 0
