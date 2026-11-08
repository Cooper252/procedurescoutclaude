"""The standard service list (one name per thing) and provider specials (D-042)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

from procedurescout_core.offers import Offer, OfferError, check, describe, price_with_offer
from procedurescout_ingest.reference import catalog
from tests.test_discovery import setup_hospitals

ROOT = Path(__file__).resolve().parent.parent / "data/reference"


def load_all(conn: Connection) -> tuple[catalog.LoadStats, catalog.LoadStats]:
    catalog.load_provider_types(conn, (ROOT / "provider_types.csv").read_text())
    services = catalog.load_services(conn, (ROOT / "service_catalog.csv").read_text())
    synonyms = catalog.load_synonyms(conn, (ROOT / "service_synonyms.csv").read_text())
    return services, synonyms


def test_standard_list_loads_with_definitions_and_provider_types(conn: Connection) -> None:
    services, synonyms = load_all(conn)
    assert services.rejects == [] and synonyms.rejects == []
    assert services.summary == {"approved": services.rows_in}  # Cooper (2026-11-08, D-042)
    assert services.rows_in > 200
    missing = conn.execute(
        text(
            """
            SELECT p.slug FROM ref.procedure p
            WHERE p.includes IS NOT NULL AND p.kind = 'service'
              AND (NOT EXISTS (
                    SELECT 1 FROM ref.procedure_provider_type t WHERE t.procedure_id = p.id))
            """
        )
    ).all()
    assert missing == []  # every proposal says what it includes and who offers it
    chiro = (
        conn.execute(
            text(
                """
            SELECT p.slug FROM ref.procedure_synonym s JOIN ref.procedure p ON p.id = s.procedure_id
            WHERE s.term_normalized IN ('back adjustment', 'back alignment')
            """
            )
        )
        .scalars()
        .all()
    )
    assert set(chiro) == {"chiropractic-adjustment-spine"}  # two words, one service


def test_bundle_packages_load(conn: Connection) -> None:
    load_all(conn)
    stats = catalog.load_bundles(conn, (ROOT / "bundles.csv").read_text())
    assert stats.rejects == []
    names = (
        conn.execute(text("SELECT slug FROM ref.procedure WHERE kind = 'bundle' ORDER BY slug"))
        .scalars()
        .all()
    )
    assert {"dental-checkup-visit", "new-patient-dental-visit"} <= set(names)


@pytest.fixture()
def listing(conn: Connection) -> str:
    setup_hospitals(conn)
    load_all(conn)
    facility = conn.execute(text("SELECT id FROM ref.facility WHERE ccn = 'SYN501'")).scalar()
    approved = conn.execute(
        text("SELECT id FROM ref.procedure WHERE slug = 'teeth-cleaning-adult'")
    ).scalar()
    return str(
        conn.execute(
            text(
                "INSERT INTO prov.listing_price (facility_id, procedure_id, regular_price) "
                "VALUES (:f, :p, 129) RETURNING id"
            ),
            {"f": facility, "p": approved},
        ).scalar()
    )


def _refused(conn: Connection, sql: str, params: dict[str, object]) -> None:
    sp = conn.begin_nested()
    with pytest.raises(DBAPIError):
        conn.execute(text(sql), params)
    sp.rollback()


def test_database_keeps_listings_and_specials_honest(conn: Connection, listing: str) -> None:
    facility = conn.execute(text("SELECT id FROM ref.facility WHERE ccn = 'SYN501'")).scalar()
    proposed = conn.execute(
        text(
            "INSERT INTO ref.procedure (consumer_name, slug, unit, source, review_state) "
            "VALUES ('Synthetic unreviewed service', 'synthetic-unreviewed', 'per_service', "
            "'ai_suggested', 'proposed') RETURNING id"
        )
    ).scalar()
    _refused(
        conn,
        "INSERT INTO prov.listing_price (facility_id, procedure_id, regular_price) "
        "VALUES (:f, :p, 90)",
        {"f": facility, "p": proposed},
    )  # only approved standard services can be priced
    offer = (
        "INSERT INTO prov.offer (listing_price_id, kind, who, offer_price, percent_off, amount_off,"
        " starts_on) VALUES (:l, :k, 'new_patients', :op, :pc, :am, '2026-11-08')"
    )
    _refused(conn, offer, {"l": listing, "k": "special_price", "op": 129, "pc": None, "am": None})
    _refused(conn, offer, {"l": listing, "k": "percent_off", "op": None, "pc": 100, "am": None})
    _refused(conn, offer, {"l": listing, "k": "amount_off", "op": None, "pc": None, "am": 200})
    _refused(conn, offer, {"l": listing, "k": "special_price", "op": 79, "pc": 10, "am": None})
    conn.execute(
        text(offer), {"l": listing, "k": "special_price", "op": 79, "pc": None, "am": None}
    )
    assert conn.execute(text("SELECT count(*) FROM prov.offer")).scalar() == 1


def test_api_role_cannot_read_provider_tables(api_engine) -> None:  # type: ignore[no-untyped-def]
    with api_engine.connect() as c, pytest.raises(DBAPIError):
        c.execute(text("SELECT count(*) FROM prov.offer"))


def test_offer_wording_and_math() -> None:
    start = date(2026, 11, 8)
    first = Offer(
        "special_price", "new_patients", start, date(2026, 12, 31), offer_price=Decimal(79)
    )
    assert describe(Decimal(129), first) == (
        "New patients: $79 (regular $129, save $50). Ends Dec 31, 2026."
    )
    pct = Offer("percent_off", "everyone", start, percent_off=Decimal(20), terms="Weekdays only.")
    assert price_with_offer(Decimal("129"), pct) == Decimal("103.2")
    assert describe(Decimal(129), pct) == (
        "Special: 20% off, $103.20 (regular $129, save $25.80). Weekdays only."
    )
    off = Offer("amount_off", "new_patients", start, amount_off=Decimal(30))
    assert price_with_offer(Decimal(129), off) == Decimal(99)
    for bad in (
        Offer("special_price", "new_patients", start, offer_price=Decimal(129)),
        Offer("percent_off", "new_patients", start, percent_off=Decimal(0)),
        Offer("amount_off", "everyone", start, amount_off=Decimal(10), offer_price=Decimal(5)),
        Offer("special_price", "friends", start, offer_price=Decimal(5)),
        Offer("special_price", "everyone", start, date(2026, 1, 1), offer_price=Decimal(5)),
    ):
        with pytest.raises(OfferError):
            check(Decimal(129), bad)
