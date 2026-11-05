from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from tests.conftest import alembic_config

SCHEMAS = {"ref", "src", "price", "fixture"}


def _schemas(url: str) -> set[str]:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            rows = c.execute(text("SELECT schema_name FROM information_schema.schemata"))
            return {r[0] for r in rows} & SCHEMAS
    finally:
        eng.dispose()


def test_migration_round_trip(migrated: str) -> None:
    cfg = alembic_config(migrated)
    command.downgrade(cfg, "base")
    assert _schemas(migrated) == set()
    command.upgrade(cfg, "head")
    assert _schemas(migrated) == SCHEMAS


def test_single_head() -> None:
    cfg = alembic_config("postgresql+psycopg://unused/unused_test")
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1
