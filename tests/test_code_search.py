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
    # real-file habits: leading zero dropped, CPT labeled HCPCS, "delivery system" devices
    ("CPT", "1961", "ANES CESAREAN DELIVERY ONLY", 32, 300),
    ("HCPCS", "59514", "CESAREAN DELIVERY ONLY", 20, 100),
    ("HCPCS", "C1874", "STENT, COATED/COVERED, WITH DELIVERY SYSTEM", 60, 900),
    ("MS-DRG", "795", "NORMAL NEWBORN", 35, 600),
    ("CPT", "62273", "INJECTION, EPIDURAL, OF BLOOD OR CLOT PATCH", 70, 900),
    ("MS-DRG", "776", "POSTPARTUM AND POST ABORTION DIAGNOSES W/O O.R. PROCEDURE", 45, 700),
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
    # a birth's own stays first, most widely published first; related stays after
    assert stays[0]["code"] == "807"
    assert stays[-1]["code"] == "776"


def test_real_file_habits_are_grouped_and_device_delivery_is_not_a_birth(conn: Connection) -> None:
    _index(conn)
    birth = {(o.code_system, o.code): o for o in find_options(conn, "birth")}
    assert ("HCPCS", "C1874") not in birth  # a stent "delivery system" is not a birth
    assert birth[("MS-DRG", "795")].group == "stay"  # newborn stay, by its code range
    assert birth[("CPT", "1961")].group == "anesthesia"  # 01961 published as "1961"
    csec = {(o.code_system, o.code): o for o in find_options(conn, "c-section")}
    assert csec[("HCPCS", "59514")].group == "surgery"  # a CPT number labeled HCPCS
    assert group_for("HCPCS", "C8901") == "imaging"


def test_short_forms_written_out_with_hospital_wording_kept() -> None:
    from procedurescout_core.code_search import plain_wording

    assert (
        plain_wording("Neuraxl lbr anes vag dlvr") == "Neuraxial labor anesthesia vaginal delivery"
    )
    assert plain_wording("HC c-section multi") == "C-section multi"


def test_birth_lists_its_own_codes_first_and_no_back_pain_injections(conn: Connection) -> None:
    _index(conn)
    opts = find_options(conn, "birth")
    keys = [(o.code_system, o.code) for o in opts]
    assert ("CPT", "62273") not in keys  # an epidural blood patch is not a birth
    stays = [k for k, o in zip(keys, opts, strict=True) if o.group == "stay"]
    # 776 has more places, but 807 is a birth stay by its code: it comes first
    assert stays.index(("MS-DRG", "807")) < stays.index(("MS-DRG", "776"))


def test_one_option_per_cpt_number_however_written(conn: Connection) -> None:
    _index(conn)
    conn.execute(
        text(
            "INSERT INTO ref.code_index (system, code, hospital_description, facilities, prices) "
            "VALUES ('CPT', '01961', 'ANESTH CESAREAN DELIVERY', 5, 9)"
        )
    )
    opts = [o for o in find_options(conn, "c-section") if o.code.lstrip("0") == "1961"]
    assert len(opts) == 1
    assert (opts[0].code_system, opts[0].code) == ("CPT", "01961")  # the standard spelling
    assert opts[0].places == 32  # the larger count, never added together


def test_a_code_search_finds_every_spelling_of_the_same_number(conn: Connection) -> None:
    from procedurescout_core.search import same_code_spellings

    for sys_, code in [("CPT", "01967"), ("CPT", "1967"), ("HCPCS", "59409")]:
        conn.execute(
            text(
                "INSERT INTO ref.code (system, code, version) "
                "VALUES (CAST(:s AS ref.code_system), :c, 'published') ON CONFLICT DO NOTHING"
            ),
            {"s": sys_, "c": code},
        )
    assert set(same_code_spellings(conn, [("CPT", "01967")])) == {("CPT", "01967"), ("CPT", "1967")}
    assert ("HCPCS", "59409") in same_code_spellings(conn, [("CPT", "59409")])
    assert same_code_spellings(conn, [("MS-DRG", "807")]) == [("MS-DRG", "807")]


def test_every_common_procedure_lists_its_own_codes_first(conn: Connection) -> None:
    from procedurescout_core.code_ranges import in_range

    _index(conn)
    for sys_, code, wording, places in [
        ("MS-DRG", "470", "MAJOR HIP AND KNEE JOINT REPLACEMENT W/O MCC", 50),
        ("CPT", "27447", "TOTAL KNEE ARTHROPLASTY", 45),
        ("CPT", "29881", "ARTHROSCOPY KNEE MENISCECTOMY", 44),
        ("CPT", "73721", "MRI LWR EXTREMITY JOINT W/O DYE", 48),
        ("HCPCS", "L1832", "KNEE ORTHOSIS ADJ JOINTS", 90),
        ("HCPCS", "G0105", "COLORECTAL SCRN; HI RISK IND", 40),
        ("CPT", "45378", "DIAGNOSTIC COLONOSCOPY", 60),
        ("CDT", "D1110", "PROPHYLAXIS - ADULT", 8),
    ]:
        conn.execute(
            text(
                "INSERT INTO ref.code_index "
                "(system, code, hospital_description, facilities, prices) "
                "VALUES (CAST(:s AS ref.code_system), :c, :w, :f, :f)"
            ),
            {"s": sys_, "c": code, "w": wording, "f": places},
        )
    knee = find_options(conn, "knee")
    keys = [(o.code_system, o.code) for o in knee]
    # the knee's own codes (stay, surgery, scope, MRI) are found even when the
    # wording doesn't say "knee"
    assert {("MS-DRG", "470"), ("CPT", "27447"), ("CPT", "73721")} <= set(keys)
    brace = next(o for o in knee if o.code == "L1832")
    assert not brace.core  # found by wording only: after the knee's own codes
    assert all(o.core for o in knee if o.code in ("27447", "29881", "73721"))
    colon = {(o.code_system, o.code): o for o in find_options(conn, "colonoscopy")}
    assert colon[("HCPCS", "G0105")].core  # letter codes have ranges too
    assert ("CDT", "D1110") in {
        (o.code_system, o.code) for o in find_options(conn, "teeth cleaning")
    }
    assert in_range("HCPCS", "1967", ("CPT", "01958", "01969"))
    assert not in_range("CPT", "G0105", ("CPT", "00100", "01999"))


def test_other_system_codes_price_a_place_only_when_it_lacks_the_own_code() -> None:
    from decimal import Decimal

    from procedurescout_core.price_store import PublishedPrice
    from procedurescout_core.search import prefer_own_codes

    def p(fid: str, sys_: str, code: str, amount: str) -> PublishedPrice:
        return PublishedPrice(
            facility_id=fid,
            price_source="hospital_file",
            code_system=sys_,
            code=code,
            description_raw=None,
            setting="inpatient",
            price_type="negotiated",
            payer_name_raw="X",
            plan_name_raw=None,
            amount=Decimal(amount),
            percentage=None,
            algorithm=None,
            methodology="case rate",
            dataset_version_id="d",
        )

    variants = {("APR-DRG", "5601"), ("MS-DRG", "775")}
    rows = {
        # publishes both: only its MS-DRG 807 price counts
        "a": [p("a", "MS-DRG", "807", "9000"), p("a", "APR-DRG", "5601", "4000")],
        # publishes only APR-DRG: priced by it, and labeled
        "b": [p("b", "APR-DRG", "5601", "8000")],
    }
    out, priced_as = prefer_own_codes(rows, variants)
    assert [x.code for x in out["a"]] == ["807"]
    assert [x.code for x in out["b"]] == ["5601"]
    assert priced_as == {"b": ("APR-DRG 5601",)}


def test_same_stay_codes_load_as_variants_and_apr_spellings_match(conn: Connection) -> None:
    from pathlib import Path

    from procedurescout_core.search import _variant_codes, same_code_spellings
    from procedurescout_ingest.reference import catalog

    ref_dir = Path(__file__).resolve().parent.parent / "data/reference"
    catalog.load_provider_types(conn, (ref_dir / "provider_types.csv").read_text())
    loaded = catalog.load_services(conn, (ref_dir / "service_catalog.csv").read_text())
    assert not loaded.rejects
    assert _variant_codes(conn, "vaginal-birth-hospital-stay") == {
        ("MS-DRG", "775"),
        ("APR-DRG", "5601"),
    }
    conn.execute(
        text(
            "INSERT INTO ref.code (system, code, version) "
            "VALUES ('APR-DRG', '560-1', 'published') ON CONFLICT DO NOTHING"
        )
    )
    assert ("APR-DRG", "560-1") in same_code_spellings(conn, [("APR-DRG", "5601")])
