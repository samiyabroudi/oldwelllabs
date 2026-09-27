"""All SQL for the funds table.

Every query names its columns explicitly (no SELECT *, no positional INSERT), so this
code keeps working when later migrations add columns it doesn't know about.
"""

from typing import Any

import psycopg
from psycopg import sql

from app.commitment import format_commitment, parse_commitment

# The commitment text column is neither read nor written: no query here names it, so this
# code keeps working when step 6 drops it. `commitment` survives only as the API field.
COLUMNS = ("id", "fund_name", "strategy", "vintage_year", "commitment_cents", "currency")
WRITABLE = ("fund_name", "strategy", "vintage_year", "commitment")

_select_list = sql.SQL(", ").join(map(sql.Identifier, COLUMNS))


def _to_columns(values: dict[str, Any]) -> dict[str, Any]:
    """Replace the API's commitment string with the columns it's stored in.

    Only commitment_cents and currency are written; the text column is left alone (NULL
    on new rows, and possibly out of date on edited ones, but nothing reads it).
    """
    if "commitment" not in values:
        return values
    values = dict(values)
    cents, currency = parse_commitment(values.pop("commitment"))
    return {**values, "commitment_cents": cents, "currency": currency}


def _to_fund(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Add the commitment display string, built from the new columns."""
    if row is None:
        return None
    return {**row, "commitment": format_commitment(row["commitment_cents"], row["currency"])}


def list_funds(conn: psycopg.Connection) -> list[dict[str, Any]]:
    query = sql.SQL("SELECT {cols} FROM funds ORDER BY id").format(cols=_select_list)
    return [_to_fund(row) for row in conn.execute(query)]


def get_fund(conn: psycopg.Connection, fund_id: int) -> dict[str, Any] | None:
    query = sql.SQL("SELECT {cols} FROM funds WHERE id = %s").format(cols=_select_list)
    return _to_fund(conn.execute(query, (fund_id,)).fetchone())


def create_fund(
    conn: psycopg.Connection, data: dict[str, Any], fund_id: int | None = None
) -> dict[str, Any]:
    """Insert a fund. `fund_id` is only passed by the seed loader to keep CSV ids."""
    values = _to_columns({col: data[col] for col in WRITABLE})
    if fund_id is not None:
        values = {"id": fund_id, **values}
    query = sql.SQL("INSERT INTO funds ({cols}) VALUES ({vals}) RETURNING {ret}").format(
        cols=sql.SQL(", ").join(map(sql.Identifier, values)),
        vals=sql.SQL(", ").join(map(sql.Placeholder, values)),
        ret=_select_list,
    )
    return _to_fund(conn.execute(query, values).fetchone())


def update_fund(
    conn: psycopg.Connection, fund_id: int, changes: dict[str, Any]
) -> dict[str, Any] | None:
    values = _to_columns({col: changes[col] for col in WRITABLE if col in changes})
    if not values:
        return get_fund(conn, fund_id)
    query = sql.SQL("UPDATE funds SET {sets} WHERE id = {id} RETURNING {ret}").format(
        sets=sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(col), sql.Placeholder(col)) for col in values
        ),
        id=sql.Placeholder("_id"),
        ret=_select_list,
    )
    return _to_fund(conn.execute(query, {**values, "_id": fund_id}).fetchone())
