from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException, status

from app import repo
from app.db import get_conn
from app.schemas import FundIn, FundOut, FundPatch

app = FastAPI(title="OWL Funds")

Conn = Annotated[psycopg.Connection, Depends(get_conn)]


@app.get("/funds", response_model=list[FundOut])
def list_funds(conn: Conn):
    return repo.list_funds(conn)


@app.get("/funds/{fund_id}", response_model=FundOut)
def get_fund(fund_id: int, conn: Conn):
    fund = repo.get_fund(conn, fund_id)
    if fund is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fund not found")
    return fund


@app.post("/funds", response_model=FundOut, status_code=status.HTTP_201_CREATED)
def create_fund(body: FundIn, conn: Conn):
    return repo.create_fund(conn, body.model_dump())


@app.patch("/funds/{fund_id}", response_model=FundOut)
def update_fund(fund_id: int, body: FundPatch, conn: Conn):
    fund = repo.update_fund(conn, fund_id, body.model_dump(exclude_none=True))
    if fund is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fund not found")
    return fund
