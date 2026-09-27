"""Cross-check two API instances that share one database.

    python3 scripts/replay_check.py http://localhost:8101 http://localhost:8102

Every write made through one instance must be read back correctly through the other.
Commitments are compared by parsed value (cents, currency) rather than raw string, so
the check still holds once the display string is rebuilt from the new columns. Whenever
a response includes commitment_cents/currency, they must agree with its commitment.
Standard library only, so it runs without the project's virtualenv.
"""

import json
import re
import sys
import urllib.request
from decimal import Decimal

failures: list[str] = []


def call(base: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as res:
        return json.load(res)


def parse(commitment: str) -> tuple[int, str]:
    text = commitment.strip()
    amount = Decimal(re.sub(r"[^0-9.]", "", text))
    return int((amount * 100).to_integral_value()), text[-3:]


def check(cond: bool, message: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + message)
    if not cond:
        failures.append(message)


def consistent(fund: dict) -> bool:
    """New columns, when present, must match the commitment string."""
    if fund.get("commitment_cents") is None and fund.get("currency") is None:
        return True
    return (fund["commitment_cents"], fund["currency"]) == parse(fund["commitment"])


def same_fund(a: dict, b: dict) -> bool:
    fields = ("id", "fund_name", "strategy", "vintage_year")
    return all(a[f] == b[f] for f in fields) and parse(a["commitment"]) == parse(b["commitment"])


def main(old: str, new: str) -> None:
    names = {old: "old", new: "new"}

    print("Existing rows")
    old_funds, new_funds = call(old, "GET", "/funds"), call(new, "GET", "/funds")
    check(len(old_funds) == len(new_funds) > 0, f"both list {len(old_funds)} funds")
    check(all(same_fund(a, b) for a, b in zip(old_funds, new_funds)), "both read identical funds")
    for base, funds in ((old, old_funds), (new, new_funds)):
        check(all(map(consistent, funds)), f"{names[base]}: new columns match commitment on every row")

    for writer, reader in ((old, new), (new, old)):
        w, r = names[writer], names[reader]
        print(f"Writes via {w}, reads via {r}")

        created = call(writer, "POST", "/funds", {
            "fund_name": f"Replay {w} Fund", "strategy": "Buyout",
            "vintage_year": 2026, "commitment": "€1,234,567.89 EUR",
        })
        check(parse(created["commitment"]) == (123456789, "EUR"), f"{w} POST returns what was sent")
        check(consistent(created), f"{w} POST response is internally consistent")
        seen = call(reader, "GET", f"/funds/{created['id']}")
        check(same_fund(created, seen), f"{r} reads {w}'s new fund #{created['id']}")
        check(consistent(seen), f"{r}'s view of it is internally consistent")

        # Change an existing seeded row's commitment: the case where stale derived columns bite.
        target = old_funds[0]["id"] if writer == old else old_funds[1]["id"]
        patched = call(writer, "PATCH", f"/funds/{target}", {"commitment": "¥500,000,000 JPY"})
        check(parse(patched["commitment"]) == (50000000000, "JPY"), f"{w} PATCH returns what was sent")
        seen = call(reader, "GET", f"/funds/{target}")
        check(same_fund(patched, seen), f"{r} reads {w}'s updated fund #{target}")
        check(consistent(seen), f"{r}'s view of it is internally consistent")

        renamed = call(writer, "PATCH", f"/funds/{target}", {"fund_name": "Renamed Only"})
        seen = call(reader, "GET", f"/funds/{target}")
        check(same_fund(renamed, seen), f"{r} reads {w}'s name-only PATCH (commitment untouched)")

    print("Final state")
    old_funds, new_funds = call(old, "GET", "/funds"), call(new, "GET", "/funds")
    check(all(same_fund(a, b) for a, b in zip(old_funds, new_funds)), "both still read identical funds")

    if failures:
        sys.exit(f"\n{len(failures)} check(s) failed")
    print("\nAll checks passed")


if __name__ == "__main__":
    main(*sys.argv[1:3])
