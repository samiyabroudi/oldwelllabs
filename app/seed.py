"""`make seed`: drop and recreate the database, migrate it, and load funds.csv.

Rows go through funds_store.create_fund, the same write path the API uses, so the seed always
writes whatever columns the current checkout's code writes.
"""

import csv
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

from app import funds_store
from app.config import DATABASE_URL
from app.db import connect

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "funds.csv"


def recreate_database() -> None:
    info = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)
    dbname = info["dbname"]
    admin_url = psycopg.conninfo.make_conninfo(DATABASE_URL, dbname="postgres")
    with psycopg.connect(admin_url, autocommit=True) as admin:
        # FORCE disconnects any running API instances so the drop can't hang.
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(dbname)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))


def migrate() -> None:
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


def load_csv() -> int:
    with CSV_PATH.open(newline="", encoding="utf-8") as f, connect() as conn:
        rows = list(csv.DictReader(f))
        for row in rows:
            funds_store.create_fund(
                conn,
                {
                    "fund_name": row["fund_name"],
                    "strategy": row["strategy"],
                    "vintage_year": int(row["vintage_year"]),
                    "commitment": row["commitment"].strip(),
                },
                fund_id=int(row["id"]),
            )
        # Rows were inserted with explicit ids; move the identity past them.
        conn.execute("SELECT setval(pg_get_serial_sequence('funds', 'id'), (SELECT max(id) FROM funds))")
    return len(rows)


if __name__ == "__main__":
    recreate_database()
    migrate()
    print(f"Seeded {load_csv()} funds from {CSV_PATH.name}")
