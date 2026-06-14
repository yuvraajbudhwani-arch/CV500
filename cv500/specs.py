"""specs.py — THE single source of every hardcoded threshold in the toolkit.

Every value below is transcribed verbatim from the embedded build spec (Section 5)
and annotated with the Part/Rule it traces to. These are authoritative.

RULES FOR THIS FILE (from the cross-cutting rules, Section 2.3):
  * Never invent, round, average, soften, or "interpret" a threshold anywhere else
    in the code. Read every threshold from here.
  * If a value a command needs is not in this file and not supplied by the user,
    the command returns NEEDS-DATA — it does not guess.

Lanes referenced throughout: A, B, B2, C (non-financial) and F (lenders).

NOTE on signs/orientation: each threshold records the *kill condition* in a plain
comment so the calling code cannot accidentally flip the inequality.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 5.1  P0 — non-screenable kills (binary). Source: spec Section 5.1 (P0).
# ---------------------------------------------------------------------------
# These are surveillance / governance kills. Each is a binary KILL when present.
# Strings are the canonical condition labels used in output and the graveyard log.
P0_KILLS = {
    # Graded Surveillance Measure list, ANY stage -> KILL.
    "gsm_any_stage": "GSM list, any stage",
    # Additional Surveillance Measure list, NEW entries -> KILL.
    "asm_new_entry": "ASM list (new entries)",
    # Audit opinion qualified / adverse / disclaimer, OR auditor resignation <= 24 months.
    "audit_opinion_or_resignation": (
        "Audit opinion qualified/adverse/disclaimer OR auditor resignation <= 24 months"
    ),
    # Credit rating "Issuer Not Cooperating" (INC) or withdrawn for non-cooperation.
    "rating_inc_or_withdrawn": "Credit rating INC or withdrawn for non-cooperation",
    # SEBI / SFIO / ED action on company or promoters.
    "sebi_sfio_ed_action": "SEBI/SFIO/ED action on company or promoters",
}
# Auditor resignation lookback used by the P0 audit kill, in months. (Section 5.1)
P0_AUDITOR_RESIGNATION_LOOKBACK_MONTHS = 24

# Announced delisting intent / open offer in motion is NOT a standard pass/kill:
# route to a tender-protocol flag. (Section 5.1, final bullet)
P0_DELISTING_OPEN_OFFER_ROUTE = "tender-protocol flag (not a standard pass/kill)"


# ---------------------------------------------------------------------------
# 5.2  P1 — binary kills, non-financial lanes A / B / B2 / C. Source: Section 5.2.
# ---------------------------------------------------------------------------

# Any promoter pledge > 0 -> KILL. Reversible: pledge prints 0 for 2 consecutive quarters.
P1_PROMOTER_PLEDGE_MAX = 0.0  # pledge fraction/percent strictly greater than this -> KILL
P1_PROMOTER_PLEDGE_PARK_TRIGGER = "pledge prints 0 for 2 consecutive quarters"

# Promoter holding < 40% -> KILL. Lane F is EXEMPT (handled in P1-F section).
P1_PROMOTER_HOLDING_MIN_PCT = 40.0  # below this (percent) -> KILL

# Reported PAT < 0 (latest FY):
#   - KILL for lanes A and C.
#   - Lane B requires PAT > 0 by definition.
#   - Lane B2 is the SOLE exception (loss permitted) and is always Grade C.
P1_PAT_MIN = 0.0  # reported PAT strictly below this -> KILL (except Lane B2)
P1_PAT_KILL_LANES = ("A", "C")           # explicit PAT<0 kill
P1_PAT_REQUIRED_POSITIVE_LANES = ("B",)  # B requires PAT>0 by definition
P1_PAT_LOSS_PERMITTED_LANES = ("B2",)    # B2 loss permitted; always Grade C
P1_B2_FIXED_GRADE = "C"

# D/E above lane maximum -> KILL. (Section 5.2)
P1_DE_MAX_BY_LANE = {
    "A": 1.5,
    "B": 2.0,
    "B2": 1.0,
    "C": 1.0,
}

# 3-yr cumulative OCF <= 0 -> KILL.
P1_CUMULATIVE_OCF_3YR_MIN = 0.0  # 3-yr cumulative OCF at or below this -> KILL
# OR cumulative OCF/PAT < 70% over 3 yrs -> KILL.
P1_OCF_TO_PAT_MIN_RATIO = 0.70   # 3-yr cumulative OCF/PAT below this -> KILL
# The OCF/PAT test is SKIPPED for Lane B2 loss years and for Lane F.
P1_OCF_TO_PAT_SKIP_LANES = ("B2", "F")

# Auditor: qualified/adverse/disclaimer, resignation <= 24m, OR audit fee absurdly
# small for company scale -> KILL. (Section 5.2; mirrors P0 audit kill at lane level.)
P1_AUDITOR_RESIGNATION_LOOKBACK_MONTHS = 24
# "Absurdly small audit fee" has no numeric threshold in the spec -> judgment input.
# Code must NOT invent one; if not supplied/observable it is NEEDS-DATA, not a pass.
P1_AUDIT_FEE_ABSURDLY_SMALL_THRESHOLD = None

# Contingent liabilities + commitments as a fraction of net worth. (Section 5.2)
#   > 50% without a credible crystallisation analysis -> KILL.
#   25%-50%                                            -> AMBER (flagged, not a kill).
P1_CONTINGENT_LIAB_KILL_PCT_OF_NETWORTH = 50.0   # strictly above -> KILL (absent analysis)
P1_CONTINGENT_LIAB_AMBER_LOW_PCT = 25.0          # [25%, 50%] -> amber band (inclusive low)

# Equity dilution > 10% cumulative over 3 yrs without commensurate capacity/earnings -> KILL.
P1_EQUITY_DILUTION_3YR_MAX_PCT = 10.0  # strictly above (percent) -> KILL absent justification


# ---------------------------------------------------------------------------
# 5.3  P1-F — lender kills, Lane F (in addition to P0). Source: Section 5.3.
# ---------------------------------------------------------------------------

# CAR < regulatory minimum + 200 bps -> KILL.
# Approximate effective floors given in spec: banks ~ < 13.5%, NBFC-ML ~ < 17%.
P1F_CAR_BUFFER_BPS = 200
P1F_CAR_EFFECTIVE_MIN_PCT = {
    "bank": 13.5,      # regulatory minimum + 200 bps (approx, per spec)
    "nbfc_ml": 17.0,   # NBFC-ML, regulatory minimum + 200 bps (approx, per spec)
}

# GNPA > 6%, OR GNPA ratio rising in 2 consecutive years -> KILL.
P1F_GNPA_MAX_PCT = 6.0                 # strictly above -> KILL
P1F_GNPA_RISING_CONSECUTIVE_YEARS = 2  # rising this many years in a row -> KILL

# Provision coverage ratio (PCR) < 50% -> KILL.
P1F_PCR_MIN_PCT = 50.0  # below this -> KILL

# RBI PCA entry, business restrictions, or governance/KYC penalty in 24m -> KILL.
P1F_RBI_ACTION_LOOKBACK_MONTHS = 24

# RBI divergence:
#   asset-classification divergence > 10% of reported GNPA, OR
#   any provisioning divergence requiring restatement
#   -> KILL (never re-park).
P1F_RBI_ASSET_CLASS_DIVERGENCE_MAX_PCT_OF_GNPA = 10.0  # strictly above -> KILL
P1F_RBI_DIVERGENCE_NEVER_REPARK = True

# NBFC loan-book CAGR > 30% sustained 3 yrs without seasoning disclosure -> KILL.
P1F_NBFC_LOANBOOK_CAGR_MAX_PCT = 30.0
P1F_NBFC_LOANBOOK_CAGR_SUSTAINED_YEARS = 3

# Wholesale/market borrowings > 70% of liabilities with top-5 lender concentration
# undisclosed -> KILL.
P1F_WHOLESALE_BORROWINGS_MAX_PCT_OF_LIABILITIES = 70.0

# NBFC promoter < 40% -> KILL (banks exempt).
P1F_NBFC_PROMOTER_HOLDING_MIN_PCT = 40.0
P1F_PROMOTER_HOLDING_EXEMPT_SUBTYPES = ("bank",)  # banks exempt from promoter<40% kill


# ---------------------------------------------------------------------------
# 5.4  Regime gauge. Source: spec Section 5.4 (Rule 7.3).
# ---------------------------------------------------------------------------
# Inputs: Nifty Smallcap 250 trailing P/E percentile and P/B percentile, each vs the
# trailing 10-year monthly series.
REGIME_INDEX = "Nifty Smallcap 250"
REGIME_LOOKBACK_YEARS = 10
REGIME_SERIES_FREQUENCY = "monthly"
REGIME_FROTHY_MIN_PCTILE = 80.0  # BOTH P/E and P/B >= 80th -> FROTHY
REGIME_CHEAP_MAX_PCTILE = 25.0   # BOTH P/E and P/B <= 25th -> CHEAP
# NORMAL = anything else, including when the two gauges disagree.
# Missing either percentile -> NEEDS-DATA.
REGIME_LABELS = ("FROTHY", "NORMAL", "CHEAP")


# ---------------------------------------------------------------------------
# 5.5  Stressed liquidity. Source: spec Section 5.5 (Rule 7.4).
# ---------------------------------------------------------------------------
# Per-name exit budget = 10 trading days x 20% participation x P25(daily delivered
# value, trailing 2 years).
LIQUIDITY_EXIT_TRADING_DAYS = 10
LIQUIDITY_PARTICIPATION_RATE = 0.20
LIQUIDITY_DELIVERED_VALUE_PERCENTILE = 25  # P25
LIQUIDITY_DELIVERED_VALUE_LOOKBACK_YEARS = 2
# A position's value at market must remain WITHIN that budget.
# Missing the P25 figure -> NEEDS-DATA.


# ---------------------------------------------------------------------------
# 5.6  P2.5 reverse-DCF triage — LOCKED point spec. Source: Section 5.6 (Rule 3.3).
# ---------------------------------------------------------------------------
# Constants are LOCKED — never choose them. The solver's only free variable is g.
P25_WACC = 0.14                  # discount rate, LOCKED
P25_TERMINAL_GROWTH = 0.04       # terminal growth, LOCKED
P25_TAX_RATE = 0.252             # 25.2%, LOCKED
P25_EXPLICIT_YEARS = 10          # 10 explicit high-growth years, then Gordon terminal
# EBIT margin held at the 5-yr median (operator supplies the 5-yr series; we take median).
P25_EBIT_MARGIN_SERIES_LEN = 5
# Reinvestment rate = g / ROIC_norm  ->  FCFF = NOPAT x (1 - g/ROIC_norm).
# Terminal reinvestment = terminal_growth / ROIC_norm.

# Triage stop (Rule 3.3), given operator-supplied conservative expectation CAGR C:
#   implied g >= C            -> STOP / already priced            (FAIL-style)
#   implied g <= 0.60 * C     -> PROCEED / pessimism priced       (PASS-style)
#   0.60*C < g < C            -> INCONCLUSIVE — operator judgment  (do NOT auto-decide)
P25_PESSIMISM_FRACTION = 0.60
P25_VERDICT_ALREADY_PRICED = "already priced"          # STOP / FAIL-style
P25_VERDICT_PESSIMISM_PRICED = "pessimism priced"      # PROCEED / PASS-style
P25_VERDICT_INCONCLUSIVE = "inconclusive — operator judgment"

# Numerical solver bounds/tolerance for g (pure-Python bisection; no scipy).
# These are computational settings, NOT thresholds: they only control root-finding
# precision and the search window for the implied CAGR.
P25_SOLVER_G_LOW = -0.99   # allow strongly negative implied growth
P25_SOLVER_G_HIGH = 5.00   # 500% — wide upper bracket; flagged if EV unreachable within
P25_SOLVER_TOL = 1e-7
P25_SOLVER_MAX_ITER = 200


# ---------------------------------------------------------------------------
# 5.7  Graveyard & watchlist schemas. Source: spec Section 5.7.
# ---------------------------------------------------------------------------
# graveyard_log: every kill / park / conscious pass. A ledger, not a tomb.
GRAVEYARD_COLUMNS = [
    "company", "ticker", "isin", "date", "price",
    "kill_phase", "kill_condition", "kill_class", "reason", "disposition",
]
GRAVEYARD_DISPOSITIONS = ("structural", "revisitable")

# park_list / watchlist: reversible kills with a checkable re-screen trigger.
PARK_LIST_COLUMNS = [
    "company", "ticker", "isin", "date_parked",
    "reason", "re_screen_trigger", "trigger_status",
]


# ---------------------------------------------------------------------------
# 6.8  monthly-scan thresholds. Source: spec Section 6.8 (Part 08 monitoring).
# ---------------------------------------------------------------------------
# Flag any promoter sale > 0.5%.
MONTHLY_PROMOTER_SALE_FLAG_PCT = 0.5
# Price-volume anomaly: price -20% in 10 sessions on >= 1.5x average delivery with no
# disclosure -> forced-investigation flag.
MONTHLY_PRICE_DROP_PCT = 20.0
MONTHLY_PRICE_DROP_SESSIONS = 10
MONTHLY_DELIVERY_MULTIPLE = 1.5


# ---------------------------------------------------------------------------
# 6.9  vault-audit Tier-1 evidence floor. Source: spec Section 6.9.
# ---------------------------------------------------------------------------
VAULT_TIER1_FLOOR = {
    "annual_reports": {"min": 5, "label": ">= 5 annual reports"},
    "concall_transcripts": {"min": 8, "max": 12, "label": "8-12 concall transcripts"},
    "rating_rationales": {"min": 2, "label": ">= 2 rating rationales"},
    "exchange_filings_months": {"min": 24, "label": "24 months of exchange filings"},
    "shareholding_quarters": {"min": 8, "label": "shareholding pattern across 8 quarters"},
    "peer_investor_presentations": {"min": 1, "label": "peer investor presentations"},
}


# ---------------------------------------------------------------------------
# fetch-filings defaults. Source: spec Section 6.1.
# ---------------------------------------------------------------------------
FETCH_DEFAULT_YEARS = 5
FETCH_QUARTERS_PER_YEAR = 4  # up to ~4 concall transcripts per fiscal year

# Corporate suffixes stripped from company names when building file/zip names.
# Source: spec Section 6.1 ("Ltd, Limited, Pvt, Private, Inc, Corporation").
COMPANY_NAME_SUFFIXES = ("Ltd", "Limited", "Pvt", "Private", "Inc", "Corporation")


# ---------------------------------------------------------------------------
# Politeness / crawler defaults. Source: cross-cutting rule Section 2.5.
# ---------------------------------------------------------------------------
CRAWL_USER_AGENT = (
    "cv500-research-bot/0.1 (+internal Indian-equities research; respects robots.txt; "
    "contact: operator)"
)
CRAWL_MIN_INTERVAL_SEC = 0.75   # ~1-2 requests/sec per host
CRAWL_TIMEOUT_SEC = 30
CRAWL_MAX_RETRIES = 2           # a couple of retries...
CRAWL_BACKOFF_BASE_SEC = 1.5    # ...with exponential backoff

# Allowed source sites (INDIAN ONLY). Used to label provenance and to guard against
# accidentally reaching for a US source. Source: spec Sections 1 and 2.
ALLOWED_SOURCE_LABELS = ("company", "BSE", "NSE", "screener", "rating-agency", "SEBI", "MCA")
# Host substrings that must NEVER be fetched. Source: spec Section 1.
FORBIDDEN_HOST_SUBSTRINGS = ("sec.gov", "edgar", "edgar-online")
