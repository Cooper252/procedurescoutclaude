"""Alembic environment. The database URL comes from the environment,
never from alembic.ini, so credentials are not committed."""

from __future__ import annotations

import os
import re

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config


def _database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", str(url).strip())


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) mode is not supported for this project")
run_migrations_online()
