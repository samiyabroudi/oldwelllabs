"""Drop NOT NULL on the commitment text column.

Revision ID: 0005
Revises: 0004

Step 5 code stops writing the text, so its inserts leave it NULL; this must be applied
before that code serves traffic. Step-4 code still writes the text, which is harmless,
and never reads it. Dropping NOT NULL is catalog-only: no scan, no rewrite.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("ALTER TABLE funds ALTER COLUMN commitment DROP NOT NULL")


def downgrade() -> None:
    # Only possible while every row still has text, i.e. before step-5 code has inserted.
    op.execute("ALTER TABLE funds ALTER COLUMN commitment SET NOT NULL")
