"""`make seed`: drop and recreate the database, migrate it, and load funds.csv.

Rows go through funds_store.create_fund, the same write path the API uses, so the seed always
writes whatever columns the current checkout's code writes. They're validated with the API's
own FundIn model first, so the seed can't store a value the API would reject (and that a later
migration couldn't parse). Validation runs before the database is dropped, so a bad CSV
leaves the existing database untouched.
"""

import csv
import sys
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from pydantic import ValidationError

from app import funds_store
from app.config import DATABASE_URL
from app.db import connect
from app.schemas import FundIn

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


def read_csv() -> list[tuple[int, dict]]:
    """Parse and validate every row; exit without touching the database if any is invalid."""
    funds, errors = [], []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                fund = FundIn.model_validate(
                    {col: row[col] for col in ("fund_name", "strategy", "vintage_year", "commitment")}
                )
                funds.append((int(row["id"]), fund.model_dump()))
            except ValidationError as e:
                detail = "; ".join(f"{err['loc'][0]}={err['input']!r}: {err['msg']}" for err in e.errors())
                errors.append(f"id={row['id']!r}: {detail}")
            except ValueError as e:  # a non-numeric id
                errors.append(f"id={row['id']!r}: {e}")
    if errors:
        sys.exit(f"{CSV_PATH.name} has invalid rows; database left unchanged:\n  " + "\n  ".join(errors))
    return funds


def load(funds: list[tuple[int, dict]]) -> None:
    with connect() as conn:
        for fund_id, fund in funds:
            funds_store.create_fund(conn, fund, fund_id=fund_id)
        # Rows were inserted with explicit ids; move the identity past them.
        conn.execute("SELECT setval(pg_get_serial_sequence('funds', 'id'), (SELECT max(id) FROM funds))")


if __name__ == "__main__":
    funds = read_csv()
    recreate_database()
    migrate()
    load(funds)
    print(f"Seeded {len(funds)} funds from {CSV_PATH.name}")
