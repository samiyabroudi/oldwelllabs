"""Drop the commitment text column (contract).

Revision ID: 0006
Revises: 0005

Deploy only after step 5 is on every instance: step-4 code still writes this column and
would fail once it's gone. Step-5 code never names it (reads or writes), so it's unaffected.

DROP COLUMN is catalog-only (the space is reclaimed as rows are rewritten), but it takes
a brief ACCESS EXCLUSIVE lock, hence the lock_timeout.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("ALTER TABLE funds DROP COLUMN commitment")


def downgrade() -> None:
    # Restores the column's shape for step-5 code (nullable, which that code never reads or
    # writes), not its data: the original strings are gone. Values could be regenerated
    # from commitment_cents/currency if an older step ever needed them.
    op.execute("ALTER TABLE funds ADD COLUMN commitment text")
