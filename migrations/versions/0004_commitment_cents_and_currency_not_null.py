"""Make commitment_cents and currency NOT NULL.

Revision ID: 0004
Revises: 0003

Safe because 0003 backfilled every row and step 2+ code dual-writes, so step-3 code
(still running while this rolls out) always supplies both columns on insert.

SET NOT NULL scans the table under an ACCESS EXCLUSIVE lock. Fine at this size; on a large
table you'd add a CHECK (... IS NOT NULL) NOT VALID constraint, VALIDATE it (no exclusive
lock), then SET NOT NULL, which Postgres 12+ proves from the constraint without a scan.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        """
        ALTER TABLE funds
            ALTER COLUMN commitment_cents SET NOT NULL,
            ALTER COLUMN currency         SET NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE funds
            ALTER COLUMN commitment_cents DROP NOT NULL,
            ALTER COLUMN currency         DROP NOT NULL
        """
    )
