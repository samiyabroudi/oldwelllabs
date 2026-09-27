"""Carry ONE database through step_0 -> step_6, testing thoroughly at every rollout.

    python3 scripts/full_chain.py

Unlike scripts/replay.sh (fresh seed per pair), history accumulates here: rows made NULL or
stale by old code in one rollout must be correct when later steps start reading new columns.

Each rollout step_{n-1} -> step_n is run the way it would be deployed:

  migrate   `make migrate` on step_n, then check the schema is what step_n expects and,
            where they hold, data invariants in SQL (e.g. every row's cents match its text).
  phase A   step_{n-1} alone against the new schema (the moment right after migrating).
  phase B   both versions serving the same database (the rollout overlap).
  phase C   step_n alone (step_{n-1} retired).

Every phase runs a suite of writes (creates, commitment edits, name-only edits, other-field
edits, invalid input that must be rejected and leave the row unchanged, 404s), and ends by
checking every row, all fields, through every serving version against `expected`, which
records what the last successful write set. Standard library only; resets the database.
"""

import csv
import itertools
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
STEPS = [f"step_{n}" for n in range(7)]
OLD_PORT, NEW_PORT = 8201, 8202
WORK = Path(tempfile.mkdtemp(prefix="owl-chain."))
FIELDS = ("fund_name", "strategy", "vintage_year")

# Columns of `funds` after each step's migrations: {column: is_nullable}.
BASE = {"id": False, "fund_name": False, "strategy": False, "vintage_year": False}
SCHEMA = {
    0: {**BASE, "commitment": False},
    1: {**BASE, "commitment": False, "commitment_cents": True, "currency": True},
    2: {**BASE, "commitment": False, "commitment_cents": True, "currency": True},
    3: {**BASE, "commitment": False, "commitment_cents": True, "currency": True},
    4: {**BASE, "commitment": False, "commitment_cents": False, "currency": False},
    5: {**BASE, "commitment": True, "commitment_cents": False, "currency": False},
    6: {**BASE, "commitment_cents": False, "currency": False},
}

INVALID = [  # each must be rejected (422) and leave the row unchanged
    ("negative commitment", {"commitment": "-$5,000 USD"}),
    ("commitment overflowing bigint", {"commitment": "$99,999,999,999,999,999 USD"}),
    ("unparseable commitment", {"commitment": "about a million"}),
    ("vintage year out of range", {"vintage_year": 99_999_999_999}),
    ("explicit null", {"fund_name": None}),
]

expected: dict[int, dict] = {}  # id -> {fund_name, strategy, vintage_year, money: (cents, currency)}
results = {"passed": 0, "failed": []}
seeded_rows = itertools.cycle(range(1, 51))
amounts = itertools.cycle(
    f"{sym}{n:,}{cents} {cur}"
    for n, (sym, cur), cents in zip(
        range(1_000_000, 10**9, 7_654_321),
        itertools.cycle([("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("¥", "JPY"), ("C$", "CAD")]),
        itertools.cycle(["", ".25", "", ".99"]),
    )
)


# --- helpers -------------------------------------------------------------------------------

def parse(text: str) -> tuple[int, str]:
    text = text.strip()
    return int((Decimal(re.sub(r"[^0-9.]", "", text)) * 100).to_integral_value()), text[-3:]


def api(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as e:
        return e.code, None


def sql(query: str) -> list[list[str]]:
    out = subprocess.check_output(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "exec", "-T", "db",
         "psql", "-U", "owl", "-d", "owl", "-At", "-F", "\t", "-c", query], text=True)
    return [line.split("\t") for line in out.splitlines() if line]


def check(cond: bool, message: str) -> bool:
    if cond:
        results["passed"] += 1
    else:
        results["failed"].append(message)
        print(f"      FAIL  {message}")
    return cond


def record(fund: dict) -> dict:
    return {**{f: fund[f] for f in FIELDS}, "money": parse(fund["commitment"])}


def matches(fund: dict | None, fund_id: int) -> bool:
    return fund is not None and fund["id"] == fund_id and record(fund) == expected[fund_id]


def consistent(fund: dict) -> bool:
    if fund.get("commitment_cents") is None and fund.get("currency") is None:
        return True  # this version doesn't expose the new columns
    return (fund["commitment_cents"], fund["currency"]) == parse(fund["commitment"])


def serve(step: str, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(["make", "serve", f"PORT={port}"], cwd=WORK / step,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/funds")
            return proc
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"{step} did not start on port {port}")


def stop(port: int) -> None:
    subprocess.run(["pkill", "-f", f"uvicorn app.main:app --port {port}"])
    time.sleep(1)


def phase(title: str):
    before = (results["passed"], len(results["failed"]))

    def done() -> None:
        passed = results["passed"] - before[0]
        failed = len(results["failed"]) - before[1]
        print(f"    {title}: {passed + failed} checks, {failed} failed")

    return done


# --- suites --------------------------------------------------------------------------------

def verify_all(port: int, who: str) -> None:
    status, funds = api(port, "GET", "/funds")
    if not check(status == 200, f"{who}: GET /funds -> {status}"):
        return
    by_id = {f["id"]: f for f in funds}
    check(set(by_id) == set(expected), f"{who}: lists exactly the {len(expected)} expected ids")
    wrong = sorted(i for i in expected if not matches(by_id.get(i), i))
    check(not wrong, f"{who}: every row's fields and commitment match the last write (wrong: {wrong})")
    bad = sorted(f["id"] for f in funds if not consistent(f))
    check(not bad, f"{who}: commitment_cents/currency agree with commitment (bad: {bad})")


def create(port: int, who: str, readers: list[tuple[int, str]]) -> int | None:
    body = {"fund_name": f"Chain {who} {len(expected) + 1}", "strategy": "Buyout",
            "vintage_year": 2026, "commitment": next(amounts)}
    status, fund = api(port, "POST", "/funds", body)
    if not check(status == 201, f"{who}: POST /funds -> {status}"):
        return None
    expected[fund["id"]] = {**{f: body[f] for f in FIELDS}, "money": parse(body["commitment"])}
    check(matches(fund, fund["id"]) and consistent(fund), f"{who}: POST response matches what was sent")
    for port_r, reader in readers:
        check(matches(api(port_r, "GET", f"/funds/{fund['id']}")[1], fund["id"]),
              f"{reader}: reads #{fund['id']} created by {who}")
    return fund["id"]


def patch(port: int, who: str, fund_id: int, changes: dict, readers: list[tuple[int, str]]) -> None:
    status, fund = api(port, "PATCH", f"/funds/{fund_id}", changes)
    if not check(status == 200, f"{who}: PATCH #{fund_id} {changes} -> {status}"):
        return
    exp = dict(expected[fund_id])
    exp.update({f: changes[f] for f in FIELDS if f in changes})
    if "commitment" in changes:
        exp["money"] = parse(changes["commitment"])
    expected[fund_id] = exp
    check(matches(fund, fund_id) and consistent(fund), f"{who}: PATCH #{fund_id} response is correct")
    for port_r, reader in readers:
        check(matches(api(port_r, "GET", f"/funds/{fund_id}")[1], fund_id),
              f"{reader}: reads #{fund_id} after {who}'s PATCH {sorted(changes)}")


def solo_suite(port: int, who: str) -> int | None:
    me = [(port, who)]
    new_id = create(port, who, me)
    patch(port, who, next(seeded_rows), {"commitment": next(amounts)}, me)
    target = next(seeded_rows)
    patch(port, who, target, {"fund_name": f"Renamed by {who}"}, me)  # commitment untouched
    patch(port, who, target, {"strategy": "Secondaries", "vintage_year": 2019}, me)
    if new_id is not None:
        patch(port, who, new_id, {"commitment": next(amounts), "fund_name": "Edited after create"}, me)
    for label, body in INVALID:
        status, _ = api(port, "PATCH", f"/funds/{target}", body)
        check(status == 422, f"{who}: rejects {label} with 422 (got {status})")
    check(matches(api(port, "GET", f"/funds/{target}")[1], target), f"{who}: rejected PATCHes left #{target} unchanged")
    status, _ = api(port, "POST", "/funds", {"fund_name": "x", "strategy": "y", "vintage_year": 2026,
                                             "commitment": "-$1 USD"})
    check(status == 422, f"{who}: rejects a POST with a negative commitment (got {status})")
    check(api(port, "GET", "/funds/999999")[0] == 404, f"{who}: GET of a missing fund -> 404")
    check(api(port, "PATCH", "/funds/999999", {"fund_name": "x"})[0] == 404, f"{who}: PATCH of a missing fund -> 404")
    verify_all(port, who)
    return new_id


def cross_suite(old: tuple[int, str], new: tuple[int, str]) -> None:
    both = [old, new]
    created = [create(old[0], old[1], both), create(new[0], new[1], both)]
    # Same row, both orders: old code writing after new code is where derived data goes stale.
    row = next(seeded_rows)
    patch(new[0], new[1], row, {"commitment": next(amounts)}, both)
    patch(old[0], old[1], row, {"commitment": next(amounts)}, both)
    row = next(seeded_rows)
    patch(old[0], old[1], row, {"commitment": next(amounts)}, both)
    patch(new[0], new[1], row, {"commitment": next(amounts)}, both)
    # Edit rows the other version created, and a name-only edit after the other's commitment edit.
    if created[1] is not None:
        patch(old[0], old[1], created[1], {"commitment": next(amounts)}, both)
    if created[0] is not None:
        patch(new[0], new[1], created[0], {"commitment": next(amounts)}, both)
        patch(old[0], old[1], created[0], {"fund_name": "Renamed by old"}, both)
    verify_all(old[0], old[1])
    verify_all(new[0], new[1])


def check_schema(n: int) -> None:
    rows = sql("SELECT column_name, is_nullable FROM information_schema.columns "
               "WHERE table_name = 'funds'")
    actual = {name: nullable == "YES" for name, nullable in rows}
    check(actual == SCHEMA[n], f"schema after step_{n} migrations is {SCHEMA[n]} (got {actual})")


def check_backfilled() -> None:
    mismatched = sql(
        "SELECT id FROM funds WHERE commitment_cents IS DISTINCT FROM "
        "round(regexp_replace(commitment, '[^0-9.]', '', 'g')::numeric * 100)::bigint "
        "OR currency IS DISTINCT FROM right(btrim(commitment), 3)")
    check(not mismatched, f"SQL: every row's commitment_cents/currency match its text "
                          f"(mismatched: {[r[0] for r in mismatched]})")


# --- the chain -----------------------------------------------------------------------------

def main() -> None:
    for step in STEPS:
        subprocess.run(["git", "worktree", "add", "--quiet", "--detach", str(WORK / step), step],
                       cwd=ROOT, check=True)
    try:
        print("== step_0: make seed")
        subprocess.run(["make", "seed"], cwd=WORK / "step_0", check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with (ROOT / "funds.csv").open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                expected[int(r["id"])] = {"fund_name": r["fund_name"], "strategy": r["strategy"],
                                          "vintage_year": int(r["vintage_year"]),
                                          "money": parse(r["commitment"])}
        done = phase("step_0 baseline")
        check_schema(0)
        serve("step_0", OLD_PORT)
        solo_suite(OLD_PORT, "step_0")
        stop(OLD_PORT)
        done()

        for n in range(1, 7):
            old, new = STEPS[n - 1], STEPS[n]
            print(f"\n== Rollout {old} -> {new}")

            done = phase(f"make migrate ({new}) + schema/data checks")
            subprocess.run(["make", "migrate"], cwd=WORK / new, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            check_schema(n)
            if n in (3, 4):  # after the backfill and while every writer dual-writes
                check_backfilled()
            done()

            done = phase(f"A: {old} alone on {new}'s schema")
            serve(old, OLD_PORT)
            solo_suite(OLD_PORT, old)
            done()

            done = phase(f"B: {old} and {new} both serving")
            serve(new, NEW_PORT)
            cross_suite((OLD_PORT, old), (NEW_PORT, new))
            done()

            done = phase(f"C: {new} alone ({old} retired)")
            stop(OLD_PORT)
            new_id = solo_suite(NEW_PORT, new)
            if n == 5:  # with no step-4 writer left, step 5's own rows must have no text at all
                texts = sql(f"SELECT commitment IS NULL FROM funds WHERE id = {new_id}")
                check(texts == [["t"]], f"SQL: #{new_id}, created and edited by {new} alone, has NULL commitment text")
            stop(NEW_PORT)
            done()
    finally:
        stop(OLD_PORT)
        stop(NEW_PORT)
        for step in STEPS:
            subprocess.run(["git", "worktree", "remove", "--force", str(WORK / step)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    failed = results["failed"]
    print(f"\n{results['passed'] + len(failed)} checks, {len(failed)} failed, {len(expected)} rows at the end")
    print("All checks passed" if not failed else "\n".join(["Failures:", *failed]))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
