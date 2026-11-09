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
