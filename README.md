# OWL Full Stack Assessment

A small funds app (Postgres, FastAPI, React) used to demonstrate a zero-downtime,
rolling-deploy-safe migration of `funds.commitment` (text like `$1,200,000 USD`)
into `commitment_cents bigint` + `currency char(3)`.

Work lives on stacked step branches (`step_0` → `step_6`),
each cut from the previous one, with one open PR per step.

## Branches and PRs

The PRs are **chained**: each step's branch is cut from the previous step's branch, and its
PR targets that branch rather than `main` (`step_0` → `main`, `step_1` → `step_0`, …,
`step_6` → `step_5`). So each PR's diff shows only what that step adds, and every branch
contains all the steps before it.

**Trying a step.** Because a branch includes everything upstream, you don't need to go
through the steps from 0 to run one: check out any step and it stands alone.

```
git checkout step_4          # or: gh pr checkout 5
make seed                    # fresh database, migrations 0001..0004, CSV loaded
make serve PORT=8000
```

To see a rollout between two steps, run `scripts/replay.sh step_3 step_4` (or check out both
side by side as described below).

**Applying the PRs.** Merge them in order, bottom-up: #1 into `main`, then #2, and so on.
When a PR is merged and its branch deleted, GitHub retargets the next PR onto `main`, and its
diff is still just that step. Merging a later PR on its own (say #5) brings in every step below
it, since its branch contains them.

**Deploying to a running system is different: steps can't be skipped.** Starting from any step
works for a fresh database, like the one `make seed` builds. On an existing database with live
traffic, each step assumes the previous one is fully deployed (see the table below).

## Migration sequence

Each step is safe to deploy while the previous step's code is still serving. Every step
needs the previous one fully deployed first; steps whose migration and code both change
apply the migration before the new code serves.

| Branch | PR | Migration | Code |
|---|---|---|---|
| `step_0` | [#1](https://github.com/samiyabroudi/oldwelllabs/pull/1) | `0001` create `funds`, `commitment text not null` | Reads/writes text |
| `step_1` | [#2](https://github.com/samiyabroudi/oldwelllabs/pull/2) | `0002` add nullable `commitment_cents`, `currency` | No change |
| `step_2` | [#3](https://github.com/samiyabroudi/oldwelllabs/pull/3) | none | Dual-writes text + new columns; reads text |
| `step_3` | [#4](https://github.com/samiyabroudi/oldwelllabs/pull/4) | `0003` backfill every row from the text | No change |
| `step_4` | [#5](https://github.com/samiyabroudi/oldwelllabs/pull/5) | `0004` new columns `NOT NULL` | Reads new columns; still dual-writes |
| `step_5` | [#6](https://github.com/samiyabroudi/oldwelllabs/pull/6) | `0005` text column nullable | Stops writing text |
| `step_6` | [#7](https://github.com/samiyabroudi/oldwelllabs/pull/7) | `0006` drop text column | No change |

Final schema: `funds(id, fund_name, strategy, vintage_year, commitment_cents bigint not null,
currency char(3) not null)`. The API still accepts and returns `commitment` as a display
string, alongside `commitment_cents` and `currency`.

## Data

We synthesized `funds.csv` because we didn't have access to the original file from Old Well.
It has the same columns (`id, fund_name, strategy, vintage_year, commitment`) and 50 rows of
commitments in the format the assignment describes, covering USD, EUR, GBP, JPY and CAD,
with and without cents (e.g. `"$21,900,000 USD"`, `"€4,304,000.29 EUR"`, `"C$10,155,000 CAD"`).

## Requirements

Docker (with Compose), [uv](https://docs.astral.sh/uv/), Node 18+.

## Commands

| Command | What it does |
|---|---|
| `make seed` | Validate `funds.csv` like the API does, then drop and recreate the database, run this checkout's migrations, and load it |
| `make migrate` | Apply every migration up to this checkout (`alembic upgrade head`) |
| `make serve PORT=8001` | Run the API on that port (default 8000) |
| `make web API_PORT=8001` | Run the React dev server (http://localhost:5173) against the API on that port |
| `make test` | Run unit tests |

`DATABASE_URL` defaults to `postgresql://owl:owl@localhost:5432/owl`.

## Replaying a rolling deploy

```
scripts/replay.sh step_0 step_1
```

Checks out both branches into temporary worktrees, runs `make seed && make migrate` on the
older one and `make migrate` on the newer one against the shared database, serves them on
ports 8101 and 8102, and cross-checks that each instance correctly reads what the other
writes (creates, commitment edits, and edits that leave the commitment alone).

`scripts/replay.sh --db-check step_2 step_3` additionally verifies in SQL that every row's
`commitment_cents`/`currency` agree with its `commitment` text. It is only meaningful for
the `step_2 → step_3` and `step_3 → step_4` pairs (see the comment in the script).

### Code before migration

```
scripts/replay.sh --code-first step_4 step_5
```

Skips `make migrate` on the newer branch, so both versions serve against the **older**
schema, as if the new code rolled out before its migration ran. Every pair passes except
`step_4 → step_5`: step-5 code inserts rows without the commitment text, which `0004`'s schema
still requires (`NOT NULL` is dropped by `0005`). So step 5 is the one step whose migration
must be applied before its code; for the others the order doesn't matter.

### Full chain

```
python3 scripts/full_chain.py
```

Where `replay.sh` reseeds for each pair, this carries **one** database through every rollout
(`step_0 → step_1 → … → step_6`) and runs each the way it would be deployed:

- **migrate**: `make migrate` on the new step, then check the schema (columns and nullability)
  is what that step expects and, after the backfill, that every row's cents match its text (SQL).
- **A**: the old step alone against the new schema.
- **B**: both steps serving: each reads the other's creates, both edit the same row in both
  orders, and each edits rows the other created.
- **C**: the new step alone, with the old one retired. After step 5, a row it created and
  edited has NULL commitment text.

Each phase creates funds, edits commitments, names, strategies and years, sends invalid input
(negative, oversized, unparseable, bad year, explicit null) that must be rejected and leave
the row unchanged, checks 404s, and finally compares every row and field, through every
serving version, with what the last write set: 638 checks in all. This is what proves history
carries forward, e.g. a row left stale by step-1 code during the `step_1 → step_2` rollout reads
correctly once step 4 switches reads to the new columns, because step 3's backfill repaired it.

### UI chain

```
uv run --no-project --with playwright python scripts/ui_chain.py
```

The same rollout-by-rollout chain, driven through the React app in a real Chrome (Playwright,
using the installed Google Chrome). Two frontends run side by side, one on the old step's API
and one on the new step's, and every write is made by filling in the form and clicking
Add, Edit or Save, and every read is the rendered table. Each phase creates and edits funds,
checks that invalid input shows a readable error and leaves the row unchanged, and compares the
whole table with what the last write set; during each overlap, each UI must show the other's
changes (329 checks). It saves screenshots of both UIs during every overlap.

## Layout

- `app/` FastAPI app. All SQL lives in `app/funds_store.py` and names its columns explicitly;
  `app/commitment.py` parses `"$1,200,000 USD"` into `(120000000, "USD")`.
- `tests/` Unit tests.
- `migrations/` Alembic, with plain-SQL migrations (no ORM models).
- `web/` Vite + React.
- `scripts/` `replay.sh` and its checker for side-by-side branch testing; `full_chain.py` for
  the whole sequence against one database; `ui_chain.py` for the same through the browser.
- `funds.csv` Synthesized sample data (see [Data](#data)).

## API

`GET /funds`, `GET /funds/{id}`, `POST /funds`, `PATCH /funds/{id}`.
`commitment` is accepted and returned as a display string (`"$1,200,000 USD"`) on every
branch; later steps only add response fields. Commitment input is validated as
`<optional symbol><amount with up to 2 decimals> <3-letter code>`, so every stored value can
be parsed by the migration. The symbol can't contain a sign (negative amounts are rejected,
not silently made positive), and the amount is capped at 15 integer digits so its value in
cents always fits in a `bigint`. `vintage_year` must be between 1900 and 2100. `PATCH` changes only
the fields sent; an explicit `null` is rejected rather than ignored.

## Out of scope

Auth, pagination, CI/CD, production deploy config, large-table tuning (batched backfills,
lock timeouts, `NOT VALID` constraints + `VALIDATE`), messier real-world commitment
formats, and frontend polish.
