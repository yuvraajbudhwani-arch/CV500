"""provenance.py — stamp every fetched file and derived number with where it came
from and when it was retrieved.

Cross-cutting rule (Section 2.4): "Provenance on everything. Stamp every fetched
file and every derived number with its source URL and retrieval timestamp, carried
into the manifest/output."
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a trailing 'Z'.

    A single, timezone-aware clock is used everywhere so timestamps in manifests
    and logs are unambiguous and comparable.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Provenance:
    """Where a fetched artefact or derived number came from."""

    source_url: str
    source_site: str = "company"          # one of specs.ALLOWED_SOURCE_LABELS
    retrieval_datetime: str = field(default_factory=now_iso)
    http_status: Optional[int] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def stamp(source_url: str, source_site: str = "company",
          http_status: Optional[int] = None, note: str = "") -> Provenance:
    """Convenience constructor that fills the retrieval timestamp at call time."""
    return Provenance(
        source_url=source_url,
        source_site=source_site,
        retrieval_datetime=now_iso(),
        http_status=http_status,
        note=note,
    )
