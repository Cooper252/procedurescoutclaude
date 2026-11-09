"""Database URLs as hosts hand them out (postgres://, postgresql://) use the
psycopg 3 driver that ProcedureScout installs."""

from __future__ import annotations

import re


def sqlalchemy_url(url: str) -> str:
    return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url.strip())
