"""Specialties: how provider types are grouped, and whether a referral is usually needed.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-11

Cooper (2026-11-11) asked for specialists (dermatologists and the rest),
psychiatrists and a referral label. ref.provider_type gets:
- grouping: the heading it is listed under in the search menu;
- referral: 'hmo' = HMO and some other plans usually need a referral from your
  main doctor (PPO and cash usually don't); 'none' = usually no referral.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE ref.provider_type ADD COLUMN grouping text")
    op.execute(
        "ALTER TABLE ref.provider_type ADD COLUMN referral text "
        "CHECK (referral IS NULL OR referral IN ('hmo', 'none'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ref.provider_type DROP COLUMN referral")
    op.execute("ALTER TABLE ref.provider_type DROP COLUMN grouping")
