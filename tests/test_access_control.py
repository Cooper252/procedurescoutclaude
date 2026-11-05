"""The API role can read published prices only; never fixtures or staged data."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from tests.conftest import insert_price, make_dataset_version, make_facility


def test_api_role_cannot_read_fixture_schema(api_engine: Engine) -> None:
    with api_engine.connect() as c, pytest.raises(ProgrammingError, match="permission denied"):
        c.execute(text("SELECT count(*) FROM fixture.synthetic_price"))


def test_api_role_cannot_read_raw_price_table(api_engine: Engine) -> None:
    with api_engine.connect() as c, pytest.raises(ProgrammingError, match="permission denied"):
        c.execute(text("SELECT count(*) FROM price.price"))


def test_api_role_cannot_write(api_engine: Engine) -> None:
    with api_engine.connect() as c, pytest.raises(ProgrammingError, match="permission denied"):
        c.execute(text("INSERT INTO ref.payer (canonical_name) VALUES ('nope')"))


def test_published_view_hides_staged_rows(engine: Engine, api_engine: Engine) -> None:
    marker = f"SYN-{uuid.uuid4().hex[:8]}"
    with engine.begin() as c:
        facility = make_facility(c, name=f"Synthetic {marker}")
        staged = make_dataset_version(c, facility, status="staged")
        insert_price(
            c, facility_id=facility, dataset_version_id=staged, code=marker, amount=Decimal(1)
        )
    try:
        with api_engine.connect() as c:
            seen = c.execute(
                text("SELECT count(*) FROM price.published_price WHERE code = :m"), {"m": marker}
            ).scalar_one()
        assert seen == 0
        with engine.begin() as c:
            c.execute(
                text(
                    "UPDATE src.dataset_version SET status='published', published_at=now() "
                    "WHERE id = :d"
                ),
                {"d": staged},
            )
        with api_engine.connect() as c:
            seen = c.execute(
                text("SELECT count(*) FROM price.published_price WHERE code = :m"), {"m": marker}
            ).scalar_one()
        assert seen == 1
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM price.price WHERE code = :m"), {"m": marker})
            c.execute(text("DELETE FROM src.dataset_version WHERE id = :d"), {"d": staged})
