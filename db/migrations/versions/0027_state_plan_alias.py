"""Insurance spellings per state (2026-11-12).

A hospital's "Anthem | Commercial" or "Blue Cross | Medi-Cal" means a
different company in each state (Anthem Nevada, Anthem Blue Cross of
California). Until now one spelling could be matched to only one plan for the
whole country, so California hospitals' "Anthem" rates were listed as Nevada's
plan. A plan alias now has a state:
- '' (empty): the spelling means this plan in every state (Aetna, Medicare);
- a state code: only for hospitals in that state, and it takes the place of
  the every-state row there.
ref.payer.only_states holds the states of insurers that cover only those
states (data/reference/payer_states.csv); their spellings are matched per state.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ref.plan_alias ADD COLUMN state_code text NOT NULL DEFAULT '' "
        "CHECK (state_code = '' OR state_code ~ '^[A-Z]{2}$')"
    )
    op.execute(
        "ALTER TABLE ref.plan_alias "
        "DROP CONSTRAINT plan_alias_raw_payer_normalized_raw_plan_normalized_key"
    )
    op.execute(
        "ALTER TABLE ref.plan_alias ADD CONSTRAINT plan_alias_spelling_state_key "
        "UNIQUE (raw_payer_normalized, raw_plan_normalized, state_code)"
    )
    op.execute(
        "ALTER TABLE ref.payer ADD COLUMN only_states text[] "
        "CHECK (only_states IS NULL OR cardinality(only_states) > 0)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ref.payer DROP COLUMN IF EXISTS only_states")
    op.execute("DELETE FROM ref.plan_alias WHERE state_code <> ''")
    op.execute("ALTER TABLE ref.plan_alias DROP CONSTRAINT IF EXISTS plan_alias_spelling_state_key")
    op.execute(
        "ALTER TABLE ref.plan_alias ADD CONSTRAINT "
        "plan_alias_raw_payer_normalized_raw_plan_normalized_key "
        "UNIQUE (raw_payer_normalized, raw_plan_normalized)"
    )
    op.execute("ALTER TABLE ref.plan_alias DROP COLUMN IF EXISTS state_code")
