"""manifest.py — writer for the fetch-filings _manifest.csv, including the MISSING
section the spec mandates at the bottom.

Manifest columns (Section 6.1):
    document_type | fiscal_year | quarter | filename | source_url | source_site |
    retrieval_datetime | validation_status

After the data rows, a MISSING section enumerates every cell in the
N-year x (AR + 4 quarters) grid that could NOT be found, with a reason
(not found / blocked / site error).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import List, Optional, TextIO

from .needsdata import MissingItem

MANIFEST_COLUMNS = [
    "document_type",
    "fiscal_year",
    "quarter",
    "filename",
    "source_url",
    "source_site",
    "retrieval_datetime",
    "validation_status",
]


@dataclass
class ManifestEntry:
    document_type: str        # "Annual Report" | "Earnings Call Transcript"
    fiscal_year: str          # e.g. "FY2025"
    quarter: str              # e.g. "Q1" (blank for ARs)
    filename: str
    source_url: str
    source_site: str          # company / BSE / NSE / screener / ...
    retrieval_datetime: str
    validation_status: str    # ok / unverified

    def row(self) -> List[str]:
        return [
            self.document_type, self.fiscal_year, self.quarter, self.filename,
            self.source_url, self.source_site, self.retrieval_datetime,
            self.validation_status,
        ]


def write_manifest(fh: TextIO, entries: List[ManifestEntry],
                   missing: Optional[List[MissingItem]] = None) -> None:
    """Write the manifest CSV (data rows + MISSING section) to an open text handle."""
    writer = csv.writer(fh)
    writer.writerow(MANIFEST_COLUMNS)
    for e in entries:
        writer.writerow(e.row())

    # MISSING section — always present, even if empty, so the reader knows it ran.
    writer.writerow([])
    writer.writerow(["MISSING"])
    writer.writerow(["item", "reason", "detail"])
    for m in (missing or []):
        writer.writerow([m.item, m.reason, m.detail])
    if not missing:
        writer.writerow(["(none)", "", "all requested grid cells were found"])


def write_manifest_file(path: str, entries: List[ManifestEntry],
                        missing: Optional[List[MissingItem]] = None) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        write_manifest(fh, entries, missing)
