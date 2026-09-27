"""Alembic environment. Migrations are plain SQL via op.execute; there are no ORM models."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import DATABASE_URL

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)


def sqlalchemy_url() -> str:
    # SQLAlchemy needs the driver named explicitly to use psycopg 3.
    return DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations_online() -> None:
    engine = create_engine(sqlalchemy_url())
    with engine.connect() as connection:
        # One transaction per migration, so a failed step never leaves a half-applied revision.
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
