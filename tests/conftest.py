"""Shared fixtures. Tests run against TEST_DATABASE_URL, which the suite
rebuilds from scratch (downgrade to empty, upgrade to head) once per run."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.exit(f"{name} is not set; copy .env.example to .env", returncode=2)
    return value


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "db" / "migrations"))
    cfg.attributes["database_url"] = url
    return cfg


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = _require("TEST_DATABASE_URL")
    assert "test" in url.rsplit("/", 1)[-1], "refusing to run against a non-test database"
    return url


@pytest.fixture(scope="session")
def migrated(test_db_url: str) -> str:
    cfg = alembic_config(test_db_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return test_db_url


@pytest.fixture(scope="session")
def engine(migrated: str) -> Iterator[Engine]:
    eng = create_engine(migrated)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    """A connection whose work is always rolled back."""
    with engine.connect() as connection:
        trans = connection.begin()
        try:
            yield connection
        finally:
            trans.rollback()


@pytest.fixture(scope="session")
def api_engine(migrated: str) -> Iterator[Engine]:
    eng = create_engine(_require("TEST_API_DATABASE_URL"))
    yield eng
    eng.dispose()


# ----------------------------------------------------------------- factories
def make_facility(conn: Connection, name: str = "Synthetic Test Hospital") -> uuid.UUID:
    return uuid.UUID(
        str(
            conn.execute(
                text(
                    "INSERT INTO ref.facility (name, facility_type, state_code) "
                    "VALUES (:n, 'acute_care_hospital', 'NV') RETURNING id"
                ),
                {"n": name},
            ).scalar_one()
        )
    )


def make_import_run(conn: Connection, facility_id: uuid.UUID) -> uuid.UUID:
    source_id = conn.execute(
        text(
            "INSERT INTO src.transparency_source (facility_id, url, discovery_method, review_note) "
            "VALUES (:f, :u, 'manual', 'synthetic test source') RETURNING id"
        ),
        {"f": facility_id, "u": f"https://example.test/{uuid.uuid4()}.json"},
    ).scalar_one()
    file_id = conn.execute(
        text(
            "INSERT INTO src.transparency_file "
            "(source_id, sha256, bytes, http_status, object_store_key) "
            "VALUES (:s, :h, 10, 200, 'test/key') RETURNING id"
        ),
        {"s": source_id, "h": uuid.uuid4().hex * 2},
    ).scalar_one()
    return uuid.UUID(
        str(
            conn.execute(
                text(
                    "INSERT INTO src.import_run (file_id, parser_version) "
                    "VALUES (:f, 'test@0') RETURNING id"
                ),
                {"f": file_id},
            ).scalar_one()
        )
    )


def make_dataset_version(
    conn: Connection, facility_id: uuid.UUID, status: str = "staged"
) -> uuid.UUID:
    run_id = make_import_run(conn, facility_id)
    published_at = "now()" if status == "published" else "NULL"
    retired_at = "now()" if status == "retired" else "NULL"
    return uuid.UUID(
        str(
            conn.execute(
                text(
                    "INSERT INTO src.dataset_version "
                    "(facility_id, import_run_id, status, published_at, retired_at) "
                    f"VALUES (:f, :r, :s, {published_at}, {retired_at}) RETURNING id"
                ),
                {"f": facility_id, "r": run_id, "s": status},
            ).scalar_one()
        )
    )


def insert_price(conn: Connection, **overrides: object) -> None:
    """Insert one price row; overrides replace the defaults below."""
    if "facility_id" not in overrides:
        overrides["facility_id"] = make_facility(conn)
    if "dataset_version_id" not in overrides:
        overrides["dataset_version_id"] = make_dataset_version(
            conn,
            overrides["facility_id"],  # type: ignore[arg-type]
        )
    row: dict[str, object] = {
        "state_code": "NV",
        "raw_row_ref": "line:2",
        "code_system": "HCPCS",
        "code": "G0121",
        "price_type": "discounted_cash",
        "amount": None,
        "percentage": None,
        "algorithm": None,
        "methodology": None,
        "payer_name_raw": None,
        "plan_name_raw": None,
        "amount_derived": False,
        "derivation_rule": None,
    }
    row.update(overrides)
    cols = ", ".join(row)
    params = ", ".join(f":{c}" for c in row)
    conn.execute(text(f"INSERT INTO price.price ({cols}) VALUES ({params})"), row)


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> Iterator[None]:
    """Each test starts with empty rate-limit counters."""
    from procedurescout_api import ratelimit

    ratelimit.reset()
    yield
