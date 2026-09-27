from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL


def connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def get_conn() -> Iterator[psycopg.Connection]:
    """FastAPI dependency: one connection per request, committed on success."""
    with connect() as conn:
        yield conn
