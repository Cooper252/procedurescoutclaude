"""One-time (and safe to repeat) setup of a hosted database (D-048).

Runs before migrations on every deploy. Using the owner connection in
DATABASE_URL it:
- enables PostGIS;
- creates the restricted API role (PS_API_ROLE, default ps_api) with the
  password in PS_API_PASSWORD, or updates that password if the role exists;
- does the same for the provider portal role (PS_PORTAL_ROLE, default
  ps_portal, password PS_PORTAL_PASSWORD) when that password is set.
Migrations then grant the API role read access to published data only, and the
portal role write access to provider pages, reviews and counts only.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "core"))

from sqlalchemy import Connection, create_engine, text

from procedurescout_core.db_url import sqlalchemy_url


def _ensure_role(conn: Connection, role: str, password: str) -> str:
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar()
    quoted = conn.execute(text("SELECT quote_literal(:p)"), {"p": password}).scalar()
    verb = "ALTER" if exists else "CREATE"
    conn.execute(text(f"{verb} ROLE {role} LOGIN PASSWORD {quoted}"))
    db = conn.execute(text("SELECT current_database()")).scalar()
    conn.execute(text(f'GRANT CONNECT ON DATABASE "{db}" TO {role}'))
    return "updated" if exists else "created"


def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL is not set")
    roles = []
    for env_role, default, env_pw, required in (
        ("PS_API_ROLE", "ps_api", "PS_API_PASSWORD", True),
        ("PS_PORTAL_ROLE", "ps_portal", "PS_PORTAL_PASSWORD", False),
    ):
        role = os.environ.get(env_role, default)
        password = os.environ.get(env_pw, "")
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
            sys.exit(f"{env_role} is not a plain role name: {role!r}")
        if not password and not required:
            continue
        if len(password) < 24:
            sys.exit(f"{env_pw} must be set (at least 24 characters)")
        roles.append((role, password))
    engine = create_engine(sqlalchemy_url(url))
    with engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")).scalar():
            conn.execute(text("CREATE EXTENSION postgis"))
        done = [f"{role} {_ensure_role(conn, role, pw)}" for role, pw in roles]
    print("database ready: postgis on; " + ", ".join(done))


if __name__ == "__main__":
    main()
