"""Add nullable commitment_cents and currency columns (expand).

Revision ID: 0002
Revises: 0001

Nullable with no default, so on Postgres 11+ this is a catalog-only change: no table
rewrite, and existing rows read the new columns as NULL. Step 0 code is unaffected
because it names its columns explicitly, and its inserts leave these columns NULL.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD COLUMN takes a brief ACCESS EXCLUSIVE lock. If a long-running query holds a
    # conflicting lock, give up rather than queue behind it and block all traffic.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        """
        ALTER TABLE funds
            ADD COLUMN commitment_cents bigint,
            ADD COLUMN currency         char(3)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE funds DROP COLUMN commitment_cents, DROP COLUMN currency")
