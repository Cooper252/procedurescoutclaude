"""Hospital websites accepted only when their own cms-hpt.txt names them (D-048)."""

from __future__ import annotations

from sqlalchemy import Connection, text

from procedurescout_ingest import website_verify as wv
from procedurescout_ingest.reference.common import LoadStats
from tests.test_discovery import setup_hospitals

TXT = (
    "location-name: SYNTHETIC VALLEY MEDICAL CENTER\n"
    "source-page-url: https://valley.example/prices\n"
    "mrf-url: https://valley.example/file.json\n"
    "contact-name: Synthetic\ncontact-email: a@valley.example\n"
)


def fetch(url: str) -> tuple[int, str]:
    if url == "https://valley.example/cms-hpt.txt":
        return 200, TXT
    if url == "https://other.example/cms-hpt.txt":
        return 200, TXT.replace("SYNTHETIC VALLEY MEDICAL CENTER", "SOMEONE ELSE HOSPITAL")
    return 404, ""


def test_only_sites_naming_the_hospital_are_accepted(conn: Connection) -> None:
    setup_hospitals(conn)
    csv_text = (
        "ccn,url,source\n"
        "SYN501,valley.example/about,search\n"  # names SYN501: accepted
        "SYN503,https://other.example,search\n"  # names someone else: refused
        "SYN504,https://none.example,search\n"  # no cms-hpt.txt: refused
        "SYN999,https://valley.example,search\n"  # unknown hospital
    )
    stats = wv.verify(conn, csv_text, fetch, LoadStats())
    assert stats.rows_loaded == 1
    assert sorted(r.rule for r in stats.rejects) == [
        "hospital_not_named",
        "no_cms_hpt_txt",
        "unknown_hospital_or_url",
    ]
    row = conn.execute(
        text(
            "SELECT website, website_evidence_url, website_reviewed_by FROM ref.facility "
            "WHERE ccn = 'SYN501'"
        )
    ).one()
    assert row == ("https://valley.example", "https://valley.example/cms-hpt.txt", wv.AUTO_REVIEWER)


def test_dolthub_candidates_page_through_and_validate() -> None:
    calls: list[str] = []

    def get_json(url: str, params: dict[str, str]) -> dict[str, object]:
        calls.append(params["q"])
        if "OFFSET 0" in params["q"]:
            rows = [{"ccn": f"29{i:04d}", "homepage": "https://h.example/"} for i in range(500)]
            rows[0] = {"ccn": "bad", "homepage": "https://x.example/"}
            return {"rows": rows}
        return {
            "rows": [
                {"ccn": "29T049", "homepage": None},
                {"ccn": "299999", "homepage": "h.example"},
            ]
        }

    text_ = wv.dolthub_candidates(get_json, "NV")
    lines = text_.strip().splitlines()
    assert lines[0] == "ccn,url,source"
    assert len(lines) == 1 + 499 + 1  # one bad CCN and one empty homepage dropped
    assert all("WHERE state = 'NV'" in q for q in calls) and len(calls) == 2
    import pytest

    with pytest.raises(ValueError):
        wv.dolthub_candidates(get_json, "NV' OR 1=1")


def test_header_address_keys_from_json_and_csv() -> None:
    js = (
        b'\xef\xbb\xbf{"hospital_name":"X","hospital_address":'
        + b'["2700 Dolbeer St, Eureka, CA 95501"]}'
    )
    assert wv.header_address_keys(js) == {"2700|95501"}
    csv_head = (
        b"hospital_name,last_updated_on,version,hospital_address\n"
        b'"X",2026-01-01,3.0.0,"10 Main St, A, NV 89001|22 Oak Ave, B, NV 89002-1234"\n'
        b"description,code|1\n"
    )
    assert wv.header_address_keys(csv_head) == {"10|89001", "22|89002"}
    assert wv.address_key("Suite 5, 10 Main", "89001") is None


def test_a_system_file_listing_the_hospitals_address_verifies_it(conn: Connection) -> None:
    """D-058: the health system lists the hospital under another name, but the
    listed price file's header gives the hospital's street address."""
    setup_hospitals(conn)
    conn.execute(
        text(
            "UPDATE ref.facility SET address_line1 = '2700 DOLBEER ST', zip5 = '95501' "
            "WHERE ccn = 'SYN503'"
        )
    )
    system_txt = (
        "location-name: Synthetic Health Desert Campus Eureka\n"
        "source-page-url: https://system.example/prices\n"
        "mrf-url: https://system.example/desert.json\n"
        "contact-name: S\ncontact-email: a@system.example\n\n"
        "location-name: Synthetic Health Somewhere Else\n"
        "source-page-url: https://system.example/prices\n"
        "mrf-url: https://system.example/else.json\n"
        "contact-name: S\ncontact-email: a@system.example\n"
    )

    def fetch2(url: str) -> tuple[int, str]:
        return (200, system_txt) if url == "https://system.example/cms-hpt.txt" else (404, "")

    heads = {
        "https://system.example/else.json": b'{"hospital_address":["1 Other Rd, Z, NV 89999"]}',
        "https://system.example/desert.json": (
            b'{"hospital_name":"Synthetic Health","hospital_address":'
            b'["2700 Dolbeer Street, Eureka, CA 95501"]}'
        ),
    }
    csv_text = "ccn,url,source\nSYN503,https://system.example,search\n"
    without = wv.verify(conn, csv_text, fetch2, LoadStats())  # name alone: refused
    assert without.rows_loaded == 0
    stats = wv.verify(conn, csv_text, fetch2, LoadStats(), head=lambda u: heads[u])
    assert stats.rows_loaded == 1 and stats.summary["verified_by_price_file_address"] == 1
    row = conn.execute(
        text(
            "SELECT f.website, f.website_evidence_url, f.website_reviewed_by, a.alias "
            "FROM ref.facility f JOIN ref.facility_alias a ON a.facility_id = f.id "
            "AND a.alias_type = 'mrf_name' WHERE f.ccn = 'SYN503'"
        )
    ).one()
    assert tuple(row) == (
        "https://system.example",
        "https://system.example/desert.json",
        wv.ADDRESS_REVIEWER,
        "Synthetic Health Desert Campus Eureka",
    )


def test_hospitals_on_no_list_are_found_by_likely_domains(conn: Connection) -> None:
    """Vermont run (2026-11-12): 7 of 17 hospitals were on no website list.
    Likely domains are tried from the name; a guess is accepted only by the
    usual check (its cms-hpt.txt names the hospital)."""
    assert "https://www.nvrh.org" in wv.guess_origins(
        "NORTHEASTERN VERMONT REGIONAL HOSPITAL", "VT"
    )
    assert "https://www.copleyvt.org" in wv.guess_origins("COPLEY HOSPITAL INC", "VT")
    assert "https://www.mountascutney.org" in wv.guess_origins("MT ASCUTNEY HOSPITAL", "VT")
    setup_hospitals(conn)
    conn.execute(text("UPDATE ref.facility SET website = NULL WHERE ccn = 'SYN503'"))
    body = "location-name: Synthetic Desert Hospital\nmrf-url: https://www.syntheticdesert.org/f.json\n"

    def fetch_many(urls: list[str]) -> dict[str, str]:
        return {u: body for u in urls if u == "https://www.syntheticdesert.org/cms-hpt.txt"}

    csv_text = wv.guessed_candidates(conn, "NV", fetch_many)
    assert "SYN503,https://www.syntheticdesert.org" in csv_text
    stats = wv.verify(conn, csv_text, lambda url: (200, body), LoadStats())
    assert stats.summary.get("verified") == 1
    site = conn.execute(text("SELECT website FROM ref.facility WHERE ccn = 'SYN503'")).scalar()
    assert site == "https://www.syntheticdesert.org"


def test_researched_sites_are_checked_like_every_candidate(conn: Connection) -> None:
    """Arizona (2026-11-17): large hospitals were on no website list. A
    researched list (state, name as CMS writes it, url) only supplies hints;
    each is still accepted only when its cms-hpt.txt names the hospital."""
    setup_hospitals(conn)
    conn.execute(text("UPDATE ref.facility SET website = NULL WHERE ccn IN ('SYN501','SYN503')"))
    listed = (
        "state,name,url,evidence\n"
        "NV,Synthetic  Valley Medical Center,https://valley.example,own site\n"
        "NV,SYNTHETIC DESERT HOSPITAL,https://other.example,own site\n"
        "AZ,SYNTHETIC VALLEY MEDICAL CENTER,https://valley.example,other state\n"
    )
    got = wv.listed_candidates(conn, listed, "NV")
    assert "SYN501,https://valley.example" in got and "SYN503,https://other.example" in got
    assert got.count("\n") == 3  # header + the two Nevada hospitals
    stats = wv.verify(conn, got, fetch, LoadStats())
    assert stats.rows_loaded == 1  # other.example names someone else
    assert [r.rule for r in stats.rejects] == ["hospital_not_named"]
    site = conn.execute(text("SELECT website FROM ref.facility WHERE ccn = 'SYN501'")).scalar()
    assert site == "https://valley.example"
    # "*": a health system's site, read once for all the state's hospitals
    conn.execute(text("UPDATE ref.facility SET website = NULL WHERE ccn = 'SYN501'"))
    sites = "state,name,url\nNV,*,valley.example\nAZ,*,https://az.example\n"
    assert wv.listed_candidates(conn, sites, "NV").count("\n") == 1  # header only
    assert wv.system_sites(sites, "NV") == ["https://valley.example"]
    stats = wv.sibling_sites(conn, "NV", fetch, LoadStats(), extra_sites=["https://valley.example"])
    assert stats.summary.get("named_on_system_site") == 1  # only the hospital it names
    site = conn.execute(text("SELECT website FROM ref.facility WHERE ccn = 'SYN501'")).scalar()
    assert site == "https://valley.example"


def test_hospitals_on_a_system_site_verified_for_another_hospital(conn: Connection) -> None:
    """Arizona (2026-11-17): Dignity Health's site, verified for one Arizona
    hospital, lists others under names CMS writes differently. They are linked by
    their price file's header address, only when it is one hospital's address."""
    setup_hospitals(conn)
    conn.execute(
        text(
            "UPDATE ref.facility SET website = NULL, address_line1 = '2700 DOLBEER ST', "
            "zip5 = '95501' WHERE ccn = 'SYN503'"
        )
    )
    conn.execute(text("UPDATE ref.facility SET website = NULL WHERE ccn <> 'SYN501'"))
    conn.execute(
        text(
            "UPDATE ref.facility SET website = 'https://system.example', "
            "website_evidence_url = 'https://system.example/cms-hpt.txt', "
            "website_reviewed_by = 'test', website_reviewed_at = now() WHERE ccn = 'SYN501'"
        )
    )
    system_txt = (
        "location-name: Synthetic Health Desert Campus\n"
        "mrf-url: https://system.example/desert.json\n\n"
        "location-name: Synthetic Health Shared Address\n"
        "mrf-url: https://system.example/shared.json\n"
    )
    heads = {
        "https://system.example/desert.json": (
            b'{"hospital_address":["2700 Dolbeer St, X, NV 95501"]}'
        ),
        # the other synthetic hospitals all share "1 TEST WAY 89990": not one hospital
        "https://system.example/shared.json": b'{"hospital_address":["1 Test Way, X, NV 89990"]}',
    }

    def fetch2(url: str) -> tuple[int, str]:
        return (200, system_txt) if url == "https://system.example/cms-hpt.txt" else (404, "")

    stats = wv.sibling_sites(conn, "NV", fetch2, LoadStats(), head=lambda u: heads[u])
    assert stats.rows_loaded == 1 and stats.summary["linked_by_price_file_address"] == 1
    row = conn.execute(
        text(
            "SELECT f.website, f.website_reviewed_by, a.alias FROM ref.facility f "
            "JOIN ref.facility_alias a ON a.facility_id = f.id AND a.alias_type = 'mrf_name' "
            "WHERE f.ccn = 'SYN503'"
        )
    ).one()
    assert tuple(row) == (
        "https://system.example",
        wv.ADDRESS_REVIEWER,
        "Synthetic Health Desert Campus",
    )
    shared = conn.execute(
        text(
            "SELECT count(*) FROM ref.facility_alias "
            "WHERE alias = 'Synthetic Health Shared Address'"
        )
    ).scalar()
    assert shared == 0
