"""Every published option for what a person types (Cooper, 2026-11-14: "I want
20 options if that's what there is")."""

from sqlalchemy import Connection, text

from procedurescout_core.code_search import clean_wording, find_options, group_for
from procedurescout_core.search import suggest

# synthetic index rows: (system, code, hospital wording, places, prices)
ROWS = [
    ("MS-DRG", "807", "VAG DELIV W/O STERIL/D&C W/O MCC/CC", 40, 900),
    ("MS-DRG", "806", "VAGINAL DELIVERY W/O STERILIZATION/D&C W CC", 38, 800),
    ("MS-DRG", "788", "CESAREAN SECTION W/O STERILIZATION W/O CC/MCC", 39, 850),
    ("APR-DRG", "5601", "VAGINAL DELIVERY", 12, 300),
    ("APR-DRG", "6401", "NEONATE BIRTH WEIGHT > 2499 GRAMS, NORMAL NEWBORN", 11, 250),
    ("CPT", "01967", "NEURAXIAL LABOR ANALGESIA/ANESTHESIA FOR PLANNED VAG DELIVERY", 30, 500),
    ("CPT", "00840", "ANES INTRAPERITONEAL LOWER ABDOMEN", 25, 400),
    ("CPT", "00790", "UPPER ABDOMINAL PROCEDURE", 20, 300),
    ("CPT", "59510", "ROUTINE OB CARE CESAREAN DELIVERY", 18, 200),
    ("CPT", "23650", "CLOSED TX SHOULDER DISLOCATION; WITHOUT ANESTHESIA", 22, 300),
    ("ICD", "10D00Z1", "Maternity Ã» C-Section", 2, 2),
    ("CDM", "Px0001", "HC C-SECTION", 1, 1),
    ("CPT", "70551", "MRI BRAIN W/O CONTRAST", 50, 1000),
]


def _index(conn: Connection) -> None:
    conn.execute(text("DELETE FROM ref.code_index"))
    for sys_, code, wording, places, prices in ROWS:
        conn.execute(
            text(
                "INSERT INTO ref.code_index "
                "(system, code, hospital_description, facilities, prices) "
                "VALUES (CAST(:s AS ref.code_system), :c, :w, :f, :p)"
            ),
            {"s": sys_, "c": code, "w": wording, "f": places, "p": prices},
        )


def test_birth_lists_every_delivery_c_section_and_newborn_option(conn: Connection) -> None:
    _index(conn)
    found = {(o.code_system, o.code): o for o in find_options(conn, "birth")}
    for key in [
        ("MS-DRG", "807"),
        ("MS-DRG", "806"),
        ("MS-DRG", "788"),
        ("APR-DRG", "5601"),
        ("APR-DRG", "6401"),
        ("CPT", "01967"),
        ("CPT", "59510"),
    ]:
        assert key in found, key
    assert ("CPT", "70551") not in found
    assert found[("MS-DRG", "807")].group == "stay"
    assert found[("CPT", "01967")].group == "anesthesia"


def test_c_section_finds_cesarean_wording_and_hospital_items_last(conn: Connection) -> None:
    _index(conn)
    opts = find_options(conn, "c-section")
    keys = [(o.code_system, o.code) for o in opts]
    assert ("MS-DRG", "788") in keys and ("CPT", "59510") in keys
    assert keys[-1] == ("CDM", "Px0001")  # one hospital's own item code: last
    icd = next(o for o in opts if o.code == "10D00Z1")
    assert "Ã" not in icd.name


def test_anesthesia_lists_the_anesthesia_section_not_without_anesthesia(conn: Connection) -> None:
    _index(conn)
    keys = [(o.code_system, o.code) for o in find_options(conn, "anesthesia")]
    # 00790's hospital wording never says "anesthesia": found by its CPT section
    assert {("CPT", "01967"), ("CPT", "00840"), ("CPT", "00790")} <= set(keys)
    assert ("CPT", "23650") not in keys


def test_search_box_offers_the_most_published_options_first(conn: Connection) -> None:
    _index(conn)
    codes = [s for s in suggest(conn, "delivery") if s.kind == "code"]
    assert codes, "codes found by widened words"
    assert not any(s.code_system == "CDM" for s in codes)


def test_groups_and_wording() -> None:
    assert group_for("CPT", "01967") == "anesthesia"
    assert group_for("CPT", "59510") == "surgery"
    assert group_for("CPT", "70551") == "imaging"
    assert group_for("CPT", "80053") == "lab"
    assert group_for("CPT", "99213") == "visit"
    assert group_for("HCPCS", "J0735") == "drug"
    assert group_for("HCPCS", "C1817") == "supply"
    assert group_for("APR-DRG", "5601") == "stay"
    assert group_for("RC", "0370") == "hospital_item"
    assert clean_wording("MRI BRAIN W/O CONTRAST") == "MRI brain w/o contrast"
    assert clean_wording("Maternity Ã» C-Section") == "Maternity - C-Section"
    assert clean_wording("Vaginal delivery") == "Vaginal delivery"


def test_api_lists_all_options_grouped(conn: Connection) -> None:
    from fastapi.testclient import TestClient

    from procedurescout_api import search_routes
    from procedurescout_api.main import app
    from tests.conftest import api_conn_for

    _index(conn)
    app.dependency_overrides[search_routes.get_conn] = api_conn_for(conn)
    try:
        r = TestClient(app).get("/v1/services/options", params={"q": "birth"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    body = r.json()
    groups = [g["group"] for g in body["groups"]]
    assert groups[0] == "stay" and "anesthesia" in groups
    assert body["total"] >= 7
    stays = body["groups"][0]["options"]
    assert [o["places"] for o in stays] == sorted((o["places"] for o in stays), reverse=True)
