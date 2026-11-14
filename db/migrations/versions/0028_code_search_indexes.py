"""Faster word searches over every published code (2026-11-14).

On the live site "knee" took 19 seconds: the word index on ref.code_index
covers every code, and most rows are hospitals' own item codes (chargemaster,
revenue, NDC, local), so a common word matched tens of thousands of rows that
all had to be sorted. A second word index covers only codes that mean the same
thing everywhere (CPT, HCPCS, DRGs, CDT, ICD...), which is what the options
list ranks; hospitals' own item codes are looked up apart, a few at a time.
The official MS-DRG and HCPCS titles in ref.code get a word index too.

Built CONCURRENTLY so reads and the loads' writes go on meanwhile.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS code_index_procedure_words_idx "
            "ON ref.code_index USING gin "
            "(to_tsvector('english', coalesce(hospital_description, ''))) "
            "WHERE system NOT IN ('CDM', 'LOCAL', 'RC', 'NDC')"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS code_title_words_idx "
            "ON ref.code USING gin (to_tsvector('english', descriptor)) "
            "WHERE system IN ('MS-DRG', 'HCPCS') AND descriptor IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ref.code_title_words_idx")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ref.code_index_procedure_words_idx")
