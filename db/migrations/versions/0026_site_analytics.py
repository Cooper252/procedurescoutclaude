"""Site analytics for the owner (Cooper, 2026-11-12: "back end analytics so I
can see everything about this site").

Privacy (SECURITY_AND_PRIVACY.md): no cookies, no IP addresses and no browsing
history are stored. Only daily totals are kept:
- stats.site_daily: page views by kind of page, devices, languages, where
  visitors came from (the referring site's name only), searches by kind,
  searches with no prices, emails sent.
- stats.visitor_seen: a one-way code for each visitor *for one day only*
  (a hash of the address and browser with a key that changes every day), so a
  day's unique visitors can be counted; visitors can't be followed from one day
  to the next. Codes older than yesterday are deleted as new visitors arrive.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-12
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role(env: str, default: str) -> str:
    role = os.environ.get(env, default)
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError(f"{env} is not a plain role name: {role!r}")
    return role


def upgrade() -> None:
    op.execute("""
    CREATE TABLE stats.site_daily (
        day     date NOT NULL,
        metric  text NOT NULL CHECK (metric IN
                ('page_view', 'visitor', 'device', 'language', 'referrer', 'search',
                 'search_no_prices', 'email_sent', 'whole_cost')),
        key     text NOT NULL DEFAULT '' CHECK (length(key) <= 120),
        count   bigint NOT NULL CHECK (count >= 0),
        PRIMARY KEY (day, metric, key)
    )""")
    op.execute("""
    CREATE TABLE stats.visitor_seen (
        day      date NOT NULL,
        visitor  char(64) NOT NULL CHECK (visitor ~ '^[0-9a-f]{64}$'),
        PRIMARY KEY (day, visitor)
    )""")
    portal_role = _role("PS_PORTAL_ROLE", "ps_portal")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{portal_role}') THEN
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON stats.site_daily, stats.visitor_seen
                     TO {portal_role}';
            EXECUTE 'GRANT DELETE ON stats.visitor_seen TO {portal_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP TABLE stats.visitor_seen")
    op.execute("DROP TABLE stats.site_daily")
