"""cli.py — entry point for the cv500 toolkit: `cv500 <command> [args]`.

Each subcommand lives in its own module under cv500/commands/ and is imported lazily
so that a single broken/unwired source never prevents an unrelated command from
running (mirrors the per-command independence the spec requires). Run `cv500 -h` for
the list of commands, or `cv500 <command> -h` for a command's options.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def _add_fetch_filings(sub):
    p = sub.add_parser("fetch-filings",
                       help="Download latest N years of annual reports + concall transcripts into a zip")
    p.add_argument("--url", required=True, help="Company main website URL")
    p.add_argument("--ticker", help="BSE/NSE symbol — fallback search key (screener.in)")
    p.add_argument("--name", help="Override the auto-detected company name used in filenames")
    p.add_argument("--years", type=int, default=5, help="Number of most-recent fiscal years (default 5)")
    p.add_argument("--out", default="./outputs", help="Working/output directory (default ./outputs)")
    p.set_defaults(_module="cv500.commands.fetch_filings")


def _add_triage_pack(sub):
    p = sub.add_parser("triage-pack",
                       help="Light fetch sufficient to run the cheap P0/P1 kill gates")
    p.add_argument("--ticker", help="BSE/NSE symbol")
    p.add_argument("--name", help="Company name")
    p.add_argument("--url", help="Company main website URL (optional)")
    p.add_argument("--screener-csv", help="Path to an uploaded screener export CSV")
    p.add_argument("--out", default="./outputs", help="Working/output directory")
    p.set_defaults(_module="cv500.commands.triage_pack")


def _add_p0_check(sub):
    p = sub.add_parser("p0-check", help="Auto-run the P0 surveillance/governance kill checks")
    p.add_argument("--ticker", help="BSE/NSE symbol")
    p.add_argument("--name", help="Company name")
    p.add_argument("--out", default="./outputs", help="Working/output directory")
    p.set_defaults(_module="cv500.commands.p0_check")


def _add_regime(sub):
    p = sub.add_parser("regime", help="Regime verdict: FROTHY / NORMAL / CHEAP (Rule 7.3)")
    p.add_argument("--pe-pctile", type=float, help="Smallcap-250 trailing P/E percentile (0-100)")
    p.add_argument("--pb-pctile", type=float, help="Smallcap-250 trailing P/B percentile (0-100)")
    p.add_argument("--series-csv", help="10-yr monthly series CSV with columns date,pe,pb")
    p.add_argument("--out", default="./outputs", help="Working/output directory")
    p.set_defaults(_module="cv500.commands.regime")


def _add_liquidity(sub):
    p = sub.add_parser("liquidity", help="Stressed-liquidity exit budget (Rule 7.4)")
    p.add_argument("--ticker", help="BSE/NSE symbol")
    p.add_argument("--delivered-csv", help="CSV of daily delivered value (columns date,delivered_value)")
    p.add_argument("--position-value", type=float, help="Position value at market to test against budget")
    p.add_argument("--out", default="./outputs", help="Working/output directory")
    p.set_defaults(_module="cv500.commands.liquidity")


def _add_p2_5(sub):
    p = sub.add_parser("p2-5", help="Locked reverse-DCF triage: implied 10-yr revenue CAGR + verdict (Rule 3.3)")
    p.add_argument("--ev", type=float, help="Current enterprise value (EV)")
    p.add_argument("--revenue", type=float,
                   help="Current (base-year) revenue R0 — needed to scale FCFF to EV")
    p.add_argument("--ebit-margin-series",
                   help="Comma-separated 5-yr EBIT-margin series (fractions or %), median is taken")
    p.add_argument("--ebit-margin-csv", help="CSV with an ebit_margin column (alternative to --ebit-margin-series)")
    p.add_argument("--roic-norm", type=float, help="Normalised ROIC (fraction, e.g. 0.18)")
    p.add_argument("--conservative-cagr", type=float, help="Operator conservative expectation CAGR C (fraction)")
    p.add_argument("--out", default="./outputs", help="Working/output directory")
    p.set_defaults(_module="cv500.commands.p2_5")


def _add_screen_ingest(sub):
    p = sub.add_parser("screen-ingest",
                       help="Dedup lane exports + cross-reference graveyard/park-list, tag hits")
    p.add_argument("--lane-csv", action="append", default=[],
                   help="Lane export CSV (repeatable, e.g. --lane-csv A.csv --lane-csv B.csv)")
    p.add_argument("--graveyard", help="graveyard_log CSV/XLSX path")
    p.add_argument("--park-list", help="park_list/watchlist CSV/XLSX path")
    p.add_argument("--out", default="./outputs", help="Working/output directory")
    p.set_defaults(_module="cv500.commands.screen_ingest")


def _add_monthly_scan(sub):
    p = sub.add_parser("monthly-scan", help="Part 08 monthly monitoring sweep across held names")
    p.add_argument("--tickers", help="Comma-separated tickers, or @file with one per line")
    p.add_argument("--price-dir",
                   help="Folder of <ticker>.csv (columns date,close,delivered_qty/_value) "
                        "to compute the price-volume anomaly deterministically")
    p.add_argument("--out", default="./outputs", help="Working/output directory")
    p.set_defaults(_module="cv500.commands.monthly_scan")


def _add_vault_audit(sub):
    p = sub.add_parser("vault-audit", help="Read-only Tier-1 evidence-floor check on a name's 00_data folder")
    p.add_argument("--folder", required=True, help="Path to <name>/00_data")
    p.set_defaults(_module="cv500.commands.vault_audit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cv500",
        description="Operator-side data-collection toolkit for Indian listed equities. "
                    "Collects, validates, organises and reports — never decides, never "
                    "fabricates. Missing data is reported as NEEDS-DATA/MISSING.",
    )
    parser.add_argument("--version", action="version", version=f"cv500 {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    _add_fetch_filings(sub)
    _add_triage_pack(sub)
    _add_p0_check(sub)
    _add_regime(sub)
    _add_liquidity(sub)
    _add_p2_5(sub)
    _add_screen_ingest(sub)
    _add_monthly_scan(sub)
    _add_vault_audit(sub)
    return parser


def _force_utf8_console() -> None:
    """Make console output UTF-8 so progress lines render on Windows (cp1252) too."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv=None) -> int:
    _force_utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2

    import importlib
    try:
        module = importlib.import_module(args._module)
    except ModuleNotFoundError as exc:
        print(f"[error] command '{args.command}' is not available yet: {exc}", file=sys.stderr)
        return 2

    return module.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
