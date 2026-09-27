# OWL Full Stack Assessment

A small funds app (Postgres, FastAPI, React) used to demonstrate a zero-downtime,
rolling-deploy-safe migration of `funds.commitment` (text like `$1,200,000 USD`)
into `commitment_cents bigint` + `currency char(3)`.

Work lives on stacked step branches (`step_0` → `step_6`),
each cut from the previous one, with one open PR per step.

## Migration sequence

Each step is safe to deploy while the previous step's code is still serving. Every step
needs the previous one fully deployed first; steps whose migration and code both change
apply the migration before the new code serves.

| Branch | Migration | Code | Why the previous step's code still works |
|---|---|---|---|
| `step_0` | `0001` create `funds`, `commitment text not null` | Reads/writes text | (baseline) |
| `step_1` | `0002` add nullable `commitment_cents`, `currency` | No change | Explicit column lists: it never sees the new columns |
| `step_2` | none | Dual-writes text + new columns; reads text | Step 1 writes text only; new columns aren't read yet |
| `step_3` | `0003` backfill every row from the text | No change | Step 2 dual-writes, so nothing can go stale after the backfill |
| `step_4` | `0004` new columns `NOT NULL` | Reads new columns; still dual-writes | Step 3 dual-writes, so the constraint holds, and still gets its text |
| `step_5` | `0005` text column nullable | Stops writing text | Step 4 still writes text (harmless) and never reads it |
| `step_6` | `0006` drop text column | No change | Step 5 never names the column |

Final schema: `funds(id, fund_name, strategy, vintage_year, commitment_cents bigint not null,
currency char(3) not null)`. The API still accepts and returns `commitment` as a display
string, alongside `commitment_cents` and `currency`.

## Requirements

Docker (with Compose), [uv](https://docs.astral.sh/uv/), Node 18+.

## Commands

| Command | What it does |
|---|---|
| `make seed` | Drop and recreate the database, run this checkout's migrations, load `funds.csv` |
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

## Layout

- `app/` FastAPI app. All SQL lives in `app/funds_store.py` and names its columns explicitly;
  `app/commitment.py` parses `"$1,200,000 USD"` into `(120000000, "USD")`.
- `tests/` Unit tests.
- `migrations/` Alembic, with plain-SQL migrations (no ORM models).
- `web/` Vite + React.
- `scripts/` `replay.sh` and its checker for side-by-side branch testing.
- `funds.csv` A generated 50-row sample; the original file was not provided.

## API

`GET /funds`, `GET /funds/{id}`, `POST /funds`, `PATCH /funds/{id}`.
`commitment` is accepted and returned as a display string (`"$1,200,000 USD"`) on every
branch; later steps only add response fields. Commitment input is validated as
`<optional symbol><amount with up to 2 decimals> <3-letter code>`, so every stored value can
be parsed by the migration.

## Out of scope

Auth, pagination, CI/CD, production deploy config, large-table tuning (batched backfills,
lock timeouts, `NOT VALID` constraints + `VALIDATE`), messier real-world commitment
formats, and frontend polish.
