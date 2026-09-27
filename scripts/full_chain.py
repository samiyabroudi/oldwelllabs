"""Carry ONE database through step_0 -> step_6, writing through both versions at every rollout.

Unlike scripts/replay.sh (fresh seed per pair), history accumulates here: rows made NULL or
stale by old code in one rollout must be correct when later steps start reading new columns.
`expected` records the (cents, currency) the most recent write set for every row, and every
row is checked against it through both versions after each rollout and at the end.

    python3 scripts/full_chain.py

Each rollout mirrors a real deploy: `make migrate` on the new step, then the old and new
code serve side by side. Writes include both orders of old/new editing the same row (the
stale-row hazard) and a create through each. Standard library only; resets the database.
"""

import csv
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
STEPS = [f"step_{n}" for n in range(7)]
OLD_PORT, NEW_PORT = 8201, 8202
WORK = Path(tempfile.mkdtemp(prefix="owl-chain."))
failures: list[str] = []
expected: dict[int, tuple[int, str]] = {}


def parse(text: str) -> tuple[int, str]:
    text = text.strip()
    return int((Decimal(re.sub(r"[^0-9.]", "", text)) * 100).to_integral_value()), text[-3:]


def run(*cmd: str, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def call(port: int, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as res:
        return json.load(res)


def serve(step: str, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(["make", "serve", f"PORT={port}"], cwd=WORK / step,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            call(port, "GET", "/funds")
            return proc
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"{step} did not start on {port}")


def stop(*procs: subprocess.Popen) -> None:
    for p in procs:
        p.terminate()
    subprocess.run(["pkill", "-f", f"uvicorn app.main:app --port ({OLD_PORT}|{NEW_PORT})"])
    time.sleep(1)


def check(cond: bool, message: str) -> None:
    print(("    ok    " if cond else "    FAIL  ") + message)
    if not cond:
        failures.append(message)


def verify(label: str, port: int) -> None:
    funds = call(port, "GET", "/funds")
    got = {f["id"]: parse(f["commitment"]) for f in funds}
    wrong = sorted(i for i in expected if got.get(i) != expected[i])
    check(not wrong and len(got) == len(expected),
          f"{label}: all {len(expected)} rows match the last write" + (f"; wrong: {wrong}" if wrong else ""))
    exposed = [f for f in funds if f.get("commitment_cents") is not None]
    if exposed:
        bad = [f["id"] for f in exposed if (f["commitment_cents"], f["currency"]) != parse(f["commitment"])]
        check(not bad, f"{label}: commitment_cents/currency match commitment" + (f"; bad: {bad}" if bad else ""))


def write(port: int, who: str, fund_id: int, commitment: str) -> None:
    call(port, "PATCH", f"/funds/{fund_id}", {"commitment": commitment})
    expected[fund_id] = parse(commitment)
    print(f"    {who} sets #{fund_id} -> {commitment}")


def main() -> None:
    for step in STEPS:
        run("git", "worktree", "add", "--quiet", "--detach", str(WORK / step), step, cwd=ROOT)
    try:
        print("== step_0: make seed")
        run("make", "seed", cwd=WORK / "step_0")
        with (ROOT / "funds.csv").open(newline="", encoding="utf-8") as f:
            expected.update({int(r["id"]): parse(r["commitment"]) for r in csv.DictReader(f)})

        amounts = iter([f"${n},000,000 USD" if n % 2 else f"€{n},500,000.25 EUR" for n in range(1, 200)])
        for n in range(1, 7):
            old, new = STEPS[n - 1], STEPS[n]
            print(f"\n== Rollout {old} -> {new}: make migrate ({new}), then both serve")
            run("make", "migrate", cwd=WORK / new)
            po, pn = serve(old, OLD_PORT), serve(new, NEW_PORT)
            try:
                base = 7 * n  # a fresh pair of seeded rows (7..43) per rollout
                # new edits, then old edits the same row: old code can leave derived data stale
                write(NEW_PORT, f"new ({new})", base, next(amounts))
                write(OLD_PORT, f"old ({old})", base, next(amounts))
                # old edits, then new edits the same row
                write(OLD_PORT, f"old ({old})", base + 1, next(amounts))
                write(NEW_PORT, f"new ({new})", base + 1, next(amounts))
                # creates through each version
                for port, who in ((OLD_PORT, f"old ({old})"), (NEW_PORT, f"new ({new})")):
                    c = next(amounts)
                    fund = call(port, "POST", "/funds", {"fund_name": f"Chain {who}", "strategy": "Buyout",
                                                         "vintage_year": 2026, "commitment": c})
                    expected[fund["id"]] = parse(c)
                    print(f"    {who} creates #{fund['id']} -> {c}")
                verify(f"read via old ({old})", OLD_PORT)
                verify(f"read via new ({new})", NEW_PORT)
            finally:
                stop(po, pn)

        print("\n== Final: step_6 alone")
        p = serve("step_6", NEW_PORT)
        try:
            verify("read via step_6", NEW_PORT)
        finally:
            stop(p)
    finally:
        for step in STEPS:
            subprocess.run(["git", "worktree", "remove", "--force", str(WORK / step)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
