"""p0-check — auto-run the P0 surveillance/governance kill checks (Sections 5.1, 6.3).

Each check is run against its Indian source. The cardinal rule (Section 6.3): any
unreachable or unparseable source -> NEEDS-DATA for that check, NEVER an assumed
"clean" PASS. Several of these sources (NSE/BSE surveillance, SEBI orders, the rating
agencies) block generic clients or publish via dynamic tables/CSVs; this command
attempts each politely, stamps real provenance, and returns NEEDS-DATA naming exactly
what a human must verify and where. Endpoint hardening is expected to iterate (Phase 2).

Checks (Section 5.1):
  * GSM list (any stage)                         -> KILL
  * ASM list (new entries)                       -> KILL
  * Rating "Issuer Not Cooperating"/withdrawn    -> KILL
  * SEBI / SFIO / ED action on company/promoters -> KILL
  * Announced delisting / open offer in motion   -> tender-protocol flag (not pass/kill)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from .. import specs
from ..core.crawl import Crawler
from ..core.needsdata import Result, needs_data, flag
from ..core.provenance import stamp
from ..core.report import print_results, write_results_csv, overall_status

_RULE = "Section 5.1 / 6.3 (P0 surveillance & governance kills)"


@dataclass
class P0Check:
    name: str
    sources: List[str]
    manual_hint: str


# Representative public sources per check. These are recorded as provenance even when
# blocked; they are the right place for a human to verify.
_CHECKS = [
    P0Check("GSM list (any stage)",
            ["https://www.nseindia.com/regulations/exchange-communication-surveillance-actions",
             "https://www.bseindia.com/markets/equity/EQReports/GSMList.aspx"],
            "confirm the name is not on any GSM stage on NSE/BSE surveillance"),
    P0Check("ASM list (new entries)",
            ["https://www.nseindia.com/reports/asm",
             "https://www.bseindia.com/markets/equity/EQReports/ShortTermASM.aspx"],
            "confirm the name is not a NEW entry on the ASM list (NSE/BSE)"),
    P0Check("Rating INC / withdrawn for non-cooperation",
            ["https://www.crisilratings.com", "https://www.icra.in",
             "https://www.careratings.com", "https://www.indiaratings.co.in"],
            "check CRISIL/ICRA/CARE/India Ratings for 'Issuer Not Cooperating' or "
            "withdrawal-for-non-cooperation on the latest rationale"),
    P0Check("SEBI / SFIO / ED action on company or promoters",
            ["https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0",
             "https://www.sebi.gov.in/enforcement/orders.html"],
            "search SEBI orders + reputable news for action against the company/promoters"),
    P0Check("Announced delisting intent / open offer in motion",
            ["https://www.bseindia.com/corporates/ann.html",
             "https://www.nseindia.com/companies-listing/corporate-filings-announcements"],
            "if a delisting/open offer is in motion, route to the tender-protocol flag "
            "(NOT a standard pass/kill)"),
]


def run(args) -> int:
    out_dir = os.path.abspath(args.out)
    results: List[Result] = []

    ident = args.ticker or args.name
    if not ident:
        results.append(needs_data("identity", "supply --ticker or --name to run P0 checks",
                                  rule=_RULE))
        print_results("p0-check", results)
        return 0

    # Fail fast: these sources mostly block or time out; we only need a provenance
    # stamp + honest NEEDS-DATA, not the payload. Short timeout, no retries.
    crawler = Crawler(verbose=True, timeout=6, max_retries=0)
    print(f"== p0-check ==  name/ticker: {ident}")

    for chk in _CHECKS:
        reached: Optional[str] = None
        last_reason = "no source reachable"
        for url in chk.sources:
            res = crawler.fetch(url)
            if res.ok:
                reached = res.final_url or url
                break
            last_reason = f"{res.reason} ({url})"

        # Even when reached, these surveillance/enforcement sources publish via dynamic
        # tables/search we do not authoritatively parse here -> NEEDS-DATA with real
        # provenance, naming the manual verification. We never assume "clean".
        prov = stamp(reached or chk.sources[0], source_site="company",
                     note=("source reached but not authoritatively parsed"
                           if reached else last_reason))
        detail = (f"{'source reachable but requires manual confirmation' if reached else 'source unreachable: ' + last_reason}"
                  f" — {chk.manual_hint}")
        results.append(needs_data(chk.name, detail, rule=_RULE, provenance=prov))

    print_results("p0-check", results)
    print("\n  NOTE: P0 sources block automated clients / publish dynamically; every "
          "check returned NEEDS-DATA rather than an assumed-clean PASS. Verify each at "
          "the stamped source URL. A confirmed hit on GSM/ASM/INC/SEBI-SFIO-ED is a KILL "
          "(Section 5.1); delisting/open-offer routes to the tender-protocol flag.")
    write_results_csv(os.path.join(out_dir, "p0_check_result.csv"), results)
    print(f"  overall: {overall_status(results)}")
    return 0
