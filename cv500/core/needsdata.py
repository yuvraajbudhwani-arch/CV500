"""needsdata.py — NEEDS-DATA / MISSING result helpers.

The most important rule in the toolkit (Section 2.1): never fabricate or guess.
When something cannot be found or computed, the tools must say so plainly and name
exactly what is missing. NEEDS-DATA is a valid, correct outcome — not a failure.

This module gives every command a single, uniform vocabulary for results so the CLI
can print and aggregate them consistently:

    PASS        -- the check ran and the condition is satisfied / clean
    KILL        -- the check ran and a kill condition fired (screening commands)
    FLAG        -- a non-kill condition worth surfacing (amber / interrupt / route)
    NEEDS_DATA  -- a required input/source was missing or unreachable; names the gap
    ERROR       -- an unexpected failure for this item (still per-item, never aborts)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from .provenance import Provenance

PASS = "PASS"
KILL = "KILL"
FLAG = "FLAG"
NEEDS_DATA = "NEEDS-DATA"
ERROR = "ERROR"

ALL_STATUSES = (PASS, KILL, FLAG, NEEDS_DATA, ERROR)


@dataclass
class Result:
    """A single per-check / per-item result.

    `name`     -- what was checked (e.g. "GSM list", "promoter pledge", "AR FY2024").
    `status`   -- one of the constants above.
    `detail`   -- human-readable explanation. For NEEDS-DATA this MUST name the gap.
    `value`    -- the observed value, when there is one.
    `threshold`-- the spec threshold compared against, when applicable.
    `rule`     -- the Part/Rule this check traces to (for auditability).
    `provenance` -- source URL + retrieval timestamp, when there is a source.
    """

    name: str
    status: str
    detail: str = ""
    value: Any = None
    threshold: Any = None
    rule: str = ""
    provenance: Optional[Provenance] = None

    def __post_init__(self) -> None:
        if self.status not in ALL_STATUSES:
            raise ValueError(
                f"Result.status must be one of {ALL_STATUSES}, got {self.status!r}"
            )
        if self.status == NEEDS_DATA and not self.detail:
            # Enforce the core promise: NEEDS-DATA must always name what is missing.
            raise ValueError("NEEDS-DATA result must name exactly what is missing (detail=).")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "value": self.value,
            "threshold": self.threshold,
            "rule": self.rule,
        }
        if self.provenance is not None:
            d["source_url"] = self.provenance.source_url
            d["source_site"] = self.provenance.source_site
            d["retrieval_datetime"] = self.provenance.retrieval_datetime
        return d


# --- convenience constructors ------------------------------------------------

def needs_data(name: str, missing: str, rule: str = "",
               provenance: Optional[Provenance] = None) -> Result:
    """Build a NEEDS-DATA result, naming exactly what is missing."""
    return Result(name=name, status=NEEDS_DATA,
                  detail=f"NEEDS-DATA: {missing}", rule=rule, provenance=provenance)


def kill(name: str, detail: str, value: Any = None, threshold: Any = None,
         rule: str = "", provenance: Optional[Provenance] = None) -> Result:
    return Result(name=name, status=KILL, detail=detail, value=value,
                  threshold=threshold, rule=rule, provenance=provenance)


def passed(name: str, detail: str = "", value: Any = None, threshold: Any = None,
           rule: str = "", provenance: Optional[Provenance] = None) -> Result:
    return Result(name=name, status=PASS, detail=detail, value=value,
                  threshold=threshold, rule=rule, provenance=provenance)


def flag(name: str, detail: str, value: Any = None, threshold: Any = None,
         rule: str = "", provenance: Optional[Provenance] = None) -> Result:
    return Result(name=name, status=FLAG, detail=detail, value=value,
                  threshold=threshold, rule=rule, provenance=provenance)


def error(name: str, detail: str, rule: str = "") -> Result:
    return Result(name=name, status=ERROR, detail=detail, rule=rule)


@dataclass
class MissingItem:
    """One cell the toolkit looked for but could not obtain.

    Used both in the fetch-filings MISSING grid and anywhere a command needs to
    enumerate gaps. `reason` is constrained to the vocabulary the spec uses.
    """

    item: str
    reason: str = "not found"   # one of: not found / blocked / site error
    detail: str = ""


# Reasons the spec names for the fetch MISSING section (Section 6.1).
REASON_NOT_FOUND = "not found"
REASON_BLOCKED = "blocked"
REASON_SITE_ERROR = "site error"


def summarize(results: List[Result]) -> Dict[str, int]:
    """Count results by status — for the one-line run summary the CLI prints."""
    counts = {s: 0 for s in ALL_STATUSES}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts
