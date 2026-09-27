"""Full chain step_0 -> step_6 driven through the React UI in a real Chrome (Playwright).

    uv run --no-project --with playwright python scripts/ui_chain.py [SCREENSHOT_DIR]

Needs Google Chrome installed (Playwright drives it via channel="chrome", so no browser
download) and web/node_modules (`make web` installs them). Resets the database.

Two Vite dev servers from the repo's web/ (identical on every branch): "old UI" on 5201 proxies
to the old step's API on 8201, "new UI" on 5202 to the new step's API on 8202. Every write is
done by filling the form and clicking Add/Edit/Save; every read is the rendered table.
Each rollout: make migrate on the new step, then A (old alone), B (both), C (new alone).
"""

import csv
import itertools
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="owl-ui-shots."))
SHOTS.mkdir(parents=True, exist_ok=True)
STEPS = [f"step_{n}" for n in range(7)]
API = {"old": 8201, "new": 8202}
UI = {"old": 5201, "new": 5202}
WORK = Path(tempfile.mkdtemp(prefix="owl-ui-chain."))

expected: dict[int, tuple] = {}  # id -> (name, strategy, year, (cents, currency))
results = {"passed": 0, "failed": []}
seeded = itertools.cycle(range(1, 51))
amounts = itertools.cycle(["$2,500,000 USD", "€3,750,000.50 EUR", "£1,200,000 GBP", "¥400,000,000 JPY",
                           "C$8,000,000.25 CAD", "$9,100,000.99 USD", "€650,000 EUR", "£12,345,678.90 GBP"])
counter = itertools.count(1)


def parse(text: str) -> tuple[int, str]:
    text = text.strip()
    return int((Decimal(re.sub(r"[^0-9.]", "", text)) * 100).to_integral_value()), text[-3:]


def check(cond: bool, msg: str) -> bool:
    if cond:
        results["passed"] += 1
    else:
        results["failed"].append(msg)
        print(f"      FAIL  {msg}")
    return cond


def wait_http(url: str) -> None:
    for _ in range(80):
        try:
            urllib.request.urlopen(url)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"{url} never came up")


def serve_api(step: str, which: str) -> None:
    subprocess.Popen(["make", "serve", f"PORT={API[which]}"], cwd=WORK / step,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_http(f"http://localhost:{API[which]}/funds")


def stop_api(which: str) -> None:
    subprocess.run(["pkill", "-f", f"uvicorn app.main:app --port {API[which]}"])
    time.sleep(1)


# --- UI actions -----------------------------------------------------------------------------

def load(page: Page, which: str) -> None:
    page.goto(f"http://localhost:{UI[which]}/")
    page.wait_for_selector("tbody tr")


def row(page: Page, fund_id: int):
    return page.locator("tbody tr").filter(has=page.locator("td:first-child", has_text=re.compile(rf"^{fund_id}$")))


def table(page: Page) -> dict[int, tuple]:
    out = {}
    for cells in page.locator("tbody tr").evaluate_all(
            "rows => rows.map(r => [...r.querySelectorAll('td')].map(td => td.innerText))"):
        out[int(cells[0])] = (cells[1], cells[2], int(cells[3]), parse(cells[4]))
    return out


def fill_and_submit(page: Page, fields: dict, button: str) -> None:
    for label, key in (("Name", "fund_name"), ("Strategy", "strategy"), ("Vintage", "vintage_year"),
                       ("Commitment", "commitment")):
        if key in fields:
            page.get_by_label(label).fill(str(fields[key]))
    page.get_by_role("button", name=button, exact=True).click()


def wait_row(page: Page, fund_id: int, timeout: float = 5.0) -> bool:
    """The table reloads asynchronously after a save; wait for the row to show expected[fund_id]."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if table(page).get(fund_id) == expected[fund_id]:
            return True
        time.sleep(0.1)
    return False


def ui_create(page: Page, who: str) -> int | None:
    n = next(counter)
    fund = {"fund_name": f"UI {who} fund {n}", "strategy": "Buyout", "vintage_year": 2026,
            "commitment": next(amounts)}
    fill_and_submit(page, fund, "Add")
    new_row = page.locator("tbody tr").filter(has_text=fund["fund_name"])
    try:
        expect(new_row).to_have_count(1, timeout=5000)
    except AssertionError:
        check(False, f"{who}: created '{fund['fund_name']}' via the form")
        return None
    fund_id = int(new_row.locator("td").first.inner_text())
    expected[fund_id] = (fund["fund_name"], "Buyout", 2026, parse(fund["commitment"]))
    check(page.locator(".error").count() == 0, f"{who}: Add shows no error")
    check(table(page).get(fund_id) == expected[fund_id], f"{who}: new fund #{fund_id} shows what was entered")
    return fund_id


def ui_edit(page: Page, who: str, fund_id: int, changes: dict) -> None:
    row(page, fund_id).get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name=f"Edit fund #{fund_id}")).to_be_visible()
    # The form is prefilled from the table; only `changes` are retyped. The UI sends every field.
    fill_and_submit(page, changes, "Save")
    expect(page.get_by_role("heading", name="Add fund")).to_be_visible(timeout=5000)
    name, strategy, year, money = expected[fund_id]
    expected[fund_id] = (changes.get("fund_name", name), changes.get("strategy", strategy),
                         int(changes.get("vintage_year", year)),
                         parse(changes["commitment"]) if "commitment" in changes else money)
    check(wait_row(page, fund_id), f"{who}: #{fund_id} shows the edit {sorted(changes)}")


def ui_rejects(page: Page, who: str, fund_id: int, changes: dict, label: str, says: str) -> None:
    before = table(page).get(fund_id)
    row(page, fund_id).get_by_role("button", name="Edit").click()
    fill_and_submit(page, changes, "Save")
    error = page.locator(".error")
    try:
        expect(error).to_be_visible(timeout=5000)
        text = error.inner_text()
        check(says in text and "\\d" not in text, f"{who}: {label} shows a readable error (got {text!r})")
    except AssertionError:
        check(False, f"{who}: {label} shows an error message")
    check(page.get_by_role("heading", name=f"Edit fund #{fund_id}").is_visible(),
          f"{who}: {label} keeps the form open for correction")
    page.get_by_role("button", name="Cancel").click()
    load(page, who_ui[who])
    check(table(page).get(fund_id) == before == expected[fund_id], f"{who}: {label} left #{fund_id} unchanged")


def verify(page: Page, who: str) -> None:
    load(page, who_ui[who])
    shown = table(page)
    check(set(shown) == set(expected), f"{who}: table lists the {len(expected)} expected funds (got {len(shown)})")
    wrong = sorted(i for i in expected if shown.get(i) != expected[i])
    check(not wrong, f"{who}: every row shows the last write (wrong: {wrong})")


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)


def solo(page: Page, who: str) -> None:
    load(page, who_ui[who])
    new_id = ui_create(page, who)
    ui_edit(page, who, next(seeded), {"commitment": next(amounts)})
    target = next(seeded)
    ui_edit(page, who, target, {"fund_name": f"Renamed in {who} UI"})
    ui_edit(page, who, target, {"strategy": "Secondaries", "vintage_year": 2019})
    if new_id:
        ui_edit(page, who, new_id, {"commitment": next(amounts), "fund_name": f"UI {who} fund edited"})
    ui_rejects(page, who, target, {"commitment": "-$5,000 USD"}, "negative commitment", "must look like $1,200,000 USD")
    ui_rejects(page, who, target, {"commitment": "lots of money"}, "unparseable commitment", "must look like $1,200,000 USD")
    ui_rejects(page, who, target, {"vintage_year": 2500}, "vintage year 2500", "less than or equal to 2100")
    verify(page, who)


def cross(old: Page, new: Page, o: str, n: str) -> None:
    load(old, "old"); load(new, "new")
    a = ui_create(old, o)
    b = ui_create(new, n)
    verify(new, n); verify(old, o)  # each UI sees the other's create
    r = next(seeded)
    load(new, "new"); ui_edit(new, n, r, {"commitment": next(amounts)})
    load(old, "old"); ui_edit(old, o, r, {"commitment": next(amounts)})  # old writes last
    r = next(seeded)
    load(old, "old"); ui_edit(old, o, r, {"commitment": next(amounts)})
    load(new, "new"); ui_edit(new, n, r, {"commitment": next(amounts)})  # new writes last
    if b:
        load(old, "old"); ui_edit(old, o, b, {"fund_name": f"{o} renamed {n}'s fund"})
    if a:
        load(new, "new"); ui_edit(new, n, a, {"commitment": next(amounts)})
    verify(old, o); verify(new, n)


def phase(title: str):
    start = (results["passed"], len(results["failed"]))

    def done():
        p, f = results["passed"] - start[0], len(results["failed"]) - start[1]
        print(f"    {title}: {p + f} checks, {f} failed")
    return done


who_ui: dict[str, str] = {}


def main() -> None:
    for step in STEPS:
        subprocess.run(["git", "worktree", "add", "--quiet", "--detach", str(WORK / step), step], cwd=ROOT, check=True)
    vites = [subprocess.Popen(["npx", "vite", "--port", str(UI[w]), "--strictPort"], cwd=ROOT / "web",
                              env={**os.environ, "API_PORT": str(API[w])},
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for w in ("old", "new")]
    try:
        for w in ("old", "new"):
            wait_http(f"http://localhost:{UI[w]}/")
        subprocess.run(["make", "seed"], cwd=WORK / "step_0", check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with (ROOT / "funds.csv").open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                expected[int(r["id"])] = (r["fund_name"], r["strategy"], int(r["vintage_year"]), parse(r["commitment"]))

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            ctx = browser.new_context(viewport={"width": 1100, "height": 900})
            old_page, new_page = ctx.new_page(), ctx.new_page()

            print("== step_0 via UI")
            done = phase("step_0 alone")
            who_ui["step_0"] = "old"
            serve_api("step_0", "old")
            solo(old_page, "step_0")
            shot(old_page, "step_0")
            stop_api("old")
            done()

            for n in range(1, 7):
                o, nw = STEPS[n - 1], STEPS[n]
                who_ui[o], who_ui[nw] = "old", "new"
                print(f"\n== Rollout {o} -> {nw} via UI")
                subprocess.run(["make", "migrate"], cwd=WORK / nw, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                done = phase(f"A: {o} UI alone on {nw}'s schema")
                serve_api(o, "old")
                solo(old_page, o)
                done()

                done = phase(f"B: {o} UI and {nw} UI side by side")
                serve_api(nw, "new")
                cross(old_page, new_page, o, nw)
                shot(old_page, f"rollout{n}_B_old_{o}")
                shot(new_page, f"rollout{n}_B_new_{nw}")
                done()

                done = phase(f"C: {nw} UI alone")
                stop_api("old")
                solo(new_page, nw)
                stop_api("new")
                done()
            browser.close()
    finally:
        stop_api("old"); stop_api("new")
        for v in vites:
            v.terminate()
        for step in STEPS:
            subprocess.run(["git", "worktree", "remove", "--force", str(WORK / step)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    failed = results["failed"]
    print(f"\n{results['passed'] + len(failed)} UI checks, {len(failed)} failed, {len(expected)} rows at the end")
    print(f"Screenshots: {SHOTS}")
    print("All checks passed" if not failed else "\n".join(["Failures:", *failed]))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
