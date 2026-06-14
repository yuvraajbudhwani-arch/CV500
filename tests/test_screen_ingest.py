"""Tests for screen-ingest dedup + memory cross-reference tagging (Section 6.7)."""

import csv

from cv500.commands import screen_ingest as si
from cv500.commands.screen_ingest import (TAG_NEW, TAG_PARK_FIRED, TAG_PARK_NOT_MET,
                                          TAG_PARK_NEEDS_DATA, TAG_GRAVE_STRUCTURAL,
                                          TAG_GRAVE_REVISITABLE)


def test_key_prefers_isin_then_ticker_then_name():
    assert si._key("Alpha Ltd", "ALPHA", "INE001A01001") == "isin:INE001A01001"
    assert si._key("Alpha Ltd", "ALPHA", "") == "tk:ALPHA"
    assert si._key("Alpha Ltd", "", "") == "nm:ALPHA"


def test_lane_from_filename():
    assert si._lane_from_filename("CV500-A.csv") == "A"
    assert si._lane_from_filename("CV500_B2.csv") == "B2"
    assert si._lane_from_filename("export-F.csv") == "F"


def test_classify_park():
    assert si._classify_park({"trigger_status": "fired"}) == TAG_PARK_FIRED
    assert si._classify_park({"trigger_status": "met"}) == TAG_PARK_FIRED
    assert si._classify_park({"trigger_status": "not met"}) == TAG_PARK_NOT_MET
    assert si._classify_park({"trigger_status": "no"}) == TAG_PARK_NOT_MET
    assert si._classify_park({"trigger_status": ""}) == TAG_PARK_NEEDS_DATA
    assert si._classify_park({"trigger_status": "needs-data"}) == TAG_PARK_NEEDS_DATA


def _write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_full_run_tags(tmp_path):
    a = tmp_path / "CV500-A.csv"
    b = tmp_path / "CV500-B.csv"
    grave = tmp_path / "graveyard_log.csv"
    park = tmp_path / "park_list.csv"
    ident = ["company", "ticker", "isin"]
    _write(a, ident, [
        ["Alpha Ltd", "ALPHA", "INE001A01001"],   # dual-lane + new
        ["Beta Ltd", "BETA", "INE002A01002"],      # graveyard structural
        ["Gamma Ltd", "GAMMA", "INE003A01003"],    # park fired
        ["Delta Ltd", "DELTA", "INE004A01004"],    # new
    ])
    _write(b, ident, [
        ["Alpha Ltd", "ALPHA", "INE001A01001"],    # dual-lane
        ["Epsilon Ltd", "EPSILON", "INE005A01005"],# park not met
        ["Zeta Ltd", "ZETA", "INE006A01006"],      # graveyard revisitable
        ["Eta Ltd", "ETA", "INE007A01007"],        # park needs-data
    ])
    _write(grave, ["company", "ticker", "isin", "date", "price", "kill_phase",
                   "kill_condition", "kill_class", "reason", "disposition"], [
        ["Beta Ltd", "BETA", "INE002A01002", "2024-03-01", "120", "P1",
         "pledge>0", "gov", "pledged", "structural"],
        ["Zeta Ltd", "ZETA", "INE006A01006", "2023-09-15", "80", "P2",
         "valuation", "qual", "expensive", "revisitable"],
    ])
    _write(park, ["company", "ticker", "isin", "date_parked", "reason",
                  "re_screen_trigger", "trigger_status"], [
        ["Gamma Ltd", "GAMMA", "INE003A01003", "2024-01-10", "pledge",
         "pledge=0 for 2 quarters", "fired"],
        ["Epsilon Ltd", "EPSILON", "INE005A01005", "2024-02-20", "D/E", "D/E<=1.5", "not met"],
        ["Eta Ltd", "ETA", "INE007A01007", "2024-04-05", "p2.5", "CAGR<=0.6C", "needs-data"],
    ])

    out = tmp_path / "out"
    out.mkdir()
    args = _Args(lane_csv=[str(a), str(b)], graveyard=str(grave),
                 park_list=str(park), out=str(out))
    rc = si.run(args)
    assert rc == 0

    hits = {}
    with open(out / "screen_ingest_hits.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            hits[row["ticker"]] = row

    assert hits["ALPHA"]["tag"] == TAG_NEW
    assert hits["ALPHA"]["dual_lane"] == "yes"
    assert hits["DELTA"]["tag"] == TAG_NEW
    assert hits["BETA"]["tag"] == TAG_GRAVE_STRUCTURAL
    assert hits["GAMMA"]["tag"] == TAG_PARK_FIRED
    assert hits["EPSILON"]["tag"] == TAG_PARK_NOT_MET
    assert hits["ZETA"]["tag"] == TAG_GRAVE_REVISITABLE
    assert hits["ETA"]["tag"] == TAG_PARK_NEEDS_DATA
    # only Alpha is dual-lane
    assert sum(1 for h in hits.values() if h["dual_lane"] == "yes") == 1
