"""Backfill commitment_cents and currency from the commitment text, for every row.

Revision ID: 0003
Revises: 0002

Deploy only after step 2 (dual-write) is running on every instance. Until then a step-1
instance can still write text-only, leaving the new columns NULL or stale.

Every row is recomputed, not just `WHERE commitment_cents IS NULL`: a step-1 instance
that edited a row's text after step 2 had filled its columns leaves them non-NULL but
wrong. The text is the source of truth, since every code version writes it.

Concurrent step-2 writes can't race this: UPDATE locks each row, and under READ
COMMITTED, if a dual-write committed first, Postgres re-evaluates the SET expressions
against that newer row version. Both sides derive the columns from the same text.

Unparseable text fails the migration loudly rather than being skipped. The API has
validated this format since step 0, so none is expected.

The parsing duplicates app/commitment.py in SQL on purpose: migrations must not import
app code, whose behaviour can change after the migration is written.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Keep in sync with COMMITMENT_PATTERN in app/schemas.py as of this revision.
PATTERN = r"^\D*(\d{1,3}(,\d{3})*|\d+)(\.\d{1,2})?\s+[A-Z]{3}$"
CENTS = r"round(regexp_replace(commitment, '[^0-9.]', '', 'g')::numeric * 100)::bigint"
CURRENCY = "right(btrim(commitment), 3)"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE
            bad text;
        BEGIN
            SELECT string_agg(format('id=%s %L', id, commitment), ', ')
              INTO bad
              FROM funds
             WHERE btrim(commitment) !~ '{PATTERN}';
            IF bad IS NOT NULL THEN
                RAISE EXCEPTION 'Unparseable commitment values: %', bad;
            END IF;
        END
        $$
        """
    )

    # IS DISTINCT FROM skips rows that are already correct (no pointless row rewrites),
    # while still catching NULLs and stale values.
    op.execute(
        f"""
        UPDATE funds
           SET commitment_cents = {CENTS},
               currency         = {CURRENCY}
         WHERE commitment_cents IS DISTINCT FROM {CENTS}
            OR currency         IS DISTINCT FROM {CURRENCY}
        """
    )


def downgrade() -> None:
    # Data-only migration: the columns keep their values, which older code ignores.
    pass
