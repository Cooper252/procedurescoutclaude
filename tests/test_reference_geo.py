"""Census lookups, the Census batch geocoder format, and facility geocoding."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Connection, text

from procedurescout_ingest.reference.census import (
    AddressRow,
    GeocodeResult,
    census_batch_geocode,
    census_geocode,
    census_single_geocode,
    load_census_lookups,
    parse_batch_response,
    parse_gazetteer,
    parse_relationship,
    parse_single_response,
)
from procedurescout_ingest.reference.common import SourceError
from procedurescout_ingest.reference.facilities import load_ascs, load_hospitals
from procedurescout_ingest.reference.geocode import geocode_facilities

FIX = Path(__file__).parent / "fixtures" / "reference"
REL = (FIX / "synthetic_zcta_county_rel.txt").read_text()
GAZ = (FIX / "synthetic_gaz_zcta_national.txt").read_text()


def test_relationship_primary_county_by_land_area() -> None:
    counties, primary = parse_relationship(REL)
    assert counties["32003"].name == "Clark County" and counties["32003"].state_code == "NV"
    assert "32510" in counties  # county part outside any ZCTA still names the county
    assert primary["89990"].county_fips == "32003" and not primary["89990"].crosses_counties
    assert primary["89991"].county_fips == "32031" and primary["89991"].crosses_counties


def test_gazetteer_parses_exact_decimals() -> None:
    gaz = parse_gazetteer(GAZ)
    assert gaz["89990"].lat == Decimal("36.100000")
    assert gaz["89990"].lon == Decimal("-115.100000")


@pytest.mark.parametrize("delimiter", ["|", ","])
def test_gazetteer_other_delimiters(delimiter: str) -> None:
    gaz = parse_gazetteer(GAZ.replace("\t", delimiter))
    assert gaz["89991"].lon == Decimal("-119.800000")


def test_gazetteer_signed_coordinates() -> None:
    signed = GAZ.replace("\t36.100000\t", "\t+36.100000\t")
    assert parse_gazetteer(signed)["89990"].lat == Decimal("36.100000")


def test_gazetteer_layout_change_fails_loudly() -> None:
    with pytest.raises(SourceError):
        parse_gazetteer("GEOID\tLAT\tLON\n89990\t1\t2\n")


def load_lookups(conn: Connection) -> None:
    load_census_lookups(conn, REL, GAZ, "NV", 2026, "synthetic")


def test_lookups_load_one_state(conn: Connection) -> None:
    stats = load_census_lookups(conn, REL, GAZ, "NV", 2026, "synthetic")
    assert stats.summary["counties"] == 3
    assert stats.rows_loaded == 2  # 89990, 89991; 90000 is in CA
    assert [r.rule for r in stats.rejects] == ["not_in_gazetteer"]  # 89993
    rows = conn.execute(text("SELECT zcta5, county_fips FROM ref.zcta ORDER BY zcta5")).all()
    assert [tuple(r) for r in rows] == [("89990", "32003"), ("89991", "32031")]


def test_batch_response_parsing() -> None:
    res = parse_batch_response((FIX / "synthetic_geocoder_response.csv").read_text())
    assert res["1"] == GeocodeResult(
        status="match",
        exact=True,
        matched_address="100 TEST WAY, LAS VEGAS, NV, 89990",
        lon=Decimal("-115.123456"),
        lat=Decimal("36.123456"),
        state_fips="32",
        county_fips3="003",
    )
    assert res["2"].status == "no_match" and res["3"].status == "tie"
    assert res["4"].exact is False


def test_batch_request_shape() -> None:
    seen: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        seen["url"] = str(request.url).encode()
        return httpx.Response(200, text='"a","x","No_Match"\n')

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        out = census_batch_geocode(
            client, [AddressRow("a", "1 Test Way", "Las Vegas", "NV", "89990")]
        )
    assert out["a"].status == "no_match"
    assert seen["url"].endswith(b"/geocoder/geographies/addressbatch")
    assert b'name="benchmark"' in seen["body"] and b"Public_AR_Current" in seen["body"]
    assert (
        b'name="addressFile"' in seen["body"] and b"a,1 Test Way,Las Vegas,NV,89990" in seen["body"]
    )


def hospital(ccn: str, address: str, zip_code: str, county: str = "CLARK") -> dict[str, str]:
    return {
        "facility_id": ccn,
        "facility_name": f"SYNTHETIC {ccn}",
        "address": address,
        "citytown": "TESTVILLE",
        "state": "NV",
        "zip_code": zip_code,
        "countyparish": county,
        "telephone_number": "",
        "hospital_type": "Acute Care Hospitals",
        "hospital_ownership": "",
        "emergency_services": "",
        "hospital_overall_rating": "",
    }


def ids(conn: Connection) -> dict[str, str]:
    return {c: str(i) for i, c in conn.execute(text("SELECT id, ccn FROM ref.facility"))}


def test_geocode_preference_order(conn: Connection) -> None:
    load_lookups(conn)
    load_hospitals(
        conn,
        [
            hospital("SYN301", "1 MATCH WAY", "89990"),  # address match, right county
            hospital("SYN302", "2 WRONG COUNTY", "89990"),  # match in another county -> ZCTA
            hospital("SYN303", "3 TIE ST", "89991", county="WASHOE"),  # tie -> ZCTA
            hospital("SYN304", "4 NOWHERE", "89999"),  # no match, ZIP not a ZCTA -> nothing
        ],
        "NV",
        date(2026, 7, 22),
    )
    fid = ids(conn)

    def fake(rows: list[AddressRow]) -> dict[str, GeocodeResult]:
        assert {r.id for r in rows} == set(fid.values())
        m = GeocodeResult("match", True, "x", Decimal("-115.1"), Decimal("36.1"), "32", "003")
        wrong = GeocodeResult("match", True, "x", Decimal("-119.8"), Decimal("39.5"), "32", "031")
        return {fid["SYN301"]: m, fid["SYN302"]: wrong, fid["SYN303"]: GeocodeResult("tie")}

    stats = geocode_facilities(conn, "NV", fake)
    got = {
        r[0]: (r[1], r[2])
        for r in conn.execute(text("SELECT ccn, geocode_precision, county_fips FROM ref.facility"))
    }
    assert got == {
        "SYN301": ("address", "32003"),
        "SYN302": ("zcta_centroid", "32003"),
        "SYN303": ("zcta_centroid", "32031"),
        "SYN304": (None, "32003"),
    }
    rules = sorted(r.rule for r in stats.rejects)
    assert rules == ["geocode_missing_result", "geocode_tie", "geocode_wrong_county", "no_location"]
    src = conn.execute(
        text("SELECT geocode_source FROM ref.facility WHERE ccn = 'SYN301'")
    ).scalar()
    assert src == "census_geocoder:Public_AR_Current/Current_Current:batch:exact"


def test_geocode_without_census_uses_zcta(conn: Connection) -> None:
    load_lookups(conn)
    load_hospitals(conn, [hospital("SYN305", "5 ANY", "89990")], "NV", None)
    stats = geocode_facilities(conn, "NV", None)
    assert stats.summary["zcta_centroid"] == 1
    lat = conn.execute(
        text("SELECT round(ST_Y(geom::geometry)::numeric, 4) FROM ref.facility")
    ).scalar()
    assert lat == Decimal("36.1000")


def test_geocode_needs_county_table(conn: Connection) -> None:
    stats = geocode_facilities(conn, "NV", None)
    assert [r.rule for r in stats.rejects] == ["no_counties"]


def test_geocoder_retries_server_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("procedurescout_ingest.reference.census.time.sleep", lambda _s: None)
    answers = [httpx.Response(502), httpx.Response(200, text='"a","x","No_Match"\n')]
    with httpx.Client(transport=httpx.MockTransport(lambda r: answers.pop(0))) as client:
        out = census_batch_geocode(client, [AddressRow("a", "1 Test Way", "X", "NV", "89990")])
    assert out["a"].status == "no_match"


def test_geocoder_gives_up_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("procedurescout_ingest.reference.census.time.sleep", lambda _s: None)
    with (
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(502))) as client,
        pytest.raises(SourceError, match="HTTP 502"),
    ):
        census_batch_geocode(client, [AddressRow("a", "1 Test Way", "X", "NV", "89990")])


def test_geocoder_outage_falls_back_to_zcta(conn: Connection) -> None:
    load_lookups(conn)
    load_hospitals(conn, [hospital("SYN306", "6 ANY", "89990")], "NV", None)

    def down(rows: list[AddressRow]) -> dict[str, GeocodeResult]:
        raise SourceError("Census geocoder failed: HTTP 502")

    stats = geocode_facilities(conn, "NV", down)
    assert stats.summary["zcta_centroid"] == 1
    assert any(r.rule == "geocoder_unavailable" for r in stats.rejects)


SINGLE_MATCH = """{"result": {"input": {}, "addressMatches": [{
  "matchedAddress": "1 TEST WAY, LAS VEGAS, NV, 89990",
  "coordinates": {"x": -115.123456789, "y": 36.123456789},
  "tigerLine": {"side": "L", "tigerLineId": "0"},
  "geographies": {"Counties": [{"STATE": "32", "COUNTY": "003", "GEOID": "32003"}]}}]}}"""


def test_single_response_parsing_uses_decimals() -> None:
    res = parse_single_response(SINGLE_MATCH)
    assert res.status == "match" and res.method == "single"
    assert res.lon == Decimal("-115.123456789") and res.lat == Decimal("36.123456789")
    assert (res.state_fips, res.county_fips3) == ("32", "003")
    assert parse_single_response('{"result": {"addressMatches": []}}').status == "no_match"
    two = '{"result": {"addressMatches": [{}, {}]}}'
    assert parse_single_response(two).status == "tie"


def test_batch_failure_falls_back_to_single(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("procedurescout_ingest.reference.census.time.sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/addressbatch"):
            return httpx.Response(502)
        assert request.url.params["street"] == "1 Test Way"
        assert request.url.params["format"] == "json"
        return httpx.Response(200, text=SINGLE_MATCH)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        out = census_geocode(client, [AddressRow("a", "1 Test Way", "Las Vegas", "NV", "89990")])
    assert out["a"].status == "match" and out["a"].method == "single"


def test_single_endpoint_down_raises() -> None:
    rows = [AddressRow(str(i), "1 Test Way", "X", "NV", "89990") for i in range(10)]
    with (
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client,
        pytest.raises(SourceError, match="one-address geocoder failed"),
    ):
        census_single_geocode(client, rows)


def test_zcta_fallback_county_only_when_zcta_in_one_county(conn: Connection) -> None:
    load_lookups(conn)
    asc = {
        "facility_id": "99C9999101",
        "facility_name": "SYNTHETIC ASC A",
        "npi": "",
        "citytown": "X",
        "state": "NV",
        "zip_code": "89990",
    }
    asc2 = {
        **asc,
        "facility_id": "99C9999102",
        "facility_name": "SYNTHETIC ASC B",
        "zip_code": "89991",
    }
    load_ascs(conn, [asc, asc2], "NV", None)
    geocode_facilities(conn, "NV", None)
    got = dict(conn.execute(text("SELECT ccn, county_fips FROM ref.facility")).all())
    assert got == {"99C9999101": "32003", "99C9999102": None}  # 89991 crosses counties


def test_outage_does_not_add_per_row_noise(conn: Connection) -> None:
    load_lookups(conn)
    load_hospitals(conn, [hospital("SYN307", "7 ANY", "89990")], "NV", None)

    def down(rows: list[AddressRow]) -> dict[str, GeocodeResult]:
        raise SourceError("down")

    stats = geocode_facilities(conn, "NV", down)
    assert [r.rule for r in stats.rejects] == ["geocoder_unavailable"]


def test_geocoding_in_saved_chunks_with_retry_next_run(conn: Connection) -> None:
    """2026-11-12: big states are geocoded in chunks saved one by one; when the
    geocoder is down (or time runs out) places get their ZIP location for now
    and the exact address is tried again on the next run."""
    import time

    from procedurescout_ingest.reference.geocode import DEFERRED

    load_lookups(conn)
    load_hospitals(
        conn,
        [hospital(f"SYN4{i:02d}", f"{i} MATCH WAY", "89990") for i in range(5)],
        "NV",
        date(2026, 7, 22),
    )
    calls: list[int] = []
    saves: list[int] = []

    def down(rows: list[AddressRow]) -> dict[str, GeocodeResult]:
        calls.append(len(rows))
        raise SourceError("down")

    geocode_facilities(conn, "NV", down, chunk_size=2, commit=lambda: saves.append(1))
    assert calls == [2, 2]  # stops asking after two failed chunks in a row
    assert len(saves) == 1 + 3  # counties, then every chunk
    sources = conn.execute(text("SELECT geocode_source FROM ref.facility")).scalars().all()
    assert all(s.startswith(DEFERRED) for s in sources)  # ZIP location for now

    def up(rows: list[AddressRow]) -> dict[str, GeocodeResult]:
        m = GeocodeResult("match", True, "x", Decimal("-115.1"), Decimal("36.1"), "32", "003")
        return {r.id: m for r in rows}

    geocode_facilities(conn, "NV", up, chunk_size=1, parallel=3)  # next run, 3 at a time
    precision = conn.execute(text("SELECT geocode_precision FROM ref.facility")).scalars().all()
    assert set(precision) == {"address"}

    load_hospitals(conn, [hospital("SYN499", "9 LATE ST", "89990")], "NV", date(2026, 7, 22))
    late = geocode_facilities(conn, "NV", up, stop_at_ns=time.monotonic_ns() - 1)
    assert "stopped_for_time" in late.summary
    src = conn.execute(
        text("SELECT geocode_source FROM ref.facility WHERE ccn = 'SYN499'")
    ).scalar_one()
    assert src.startswith(DEFERRED)  # out of time: ZIP now, address next run
