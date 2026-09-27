# OWL Full Stack Assessment

A small funds app (Postgres, FastAPI, React) used to demonstrate a zero-downtime,
rolling-deploy-safe migration of `funds.commitment` (text like `$1,200,000 USD`)
into `commitment_cents bigint` + `currency char(3)`.

Work lives on stacked step branches (`step_0` → `step_6`),
each cut from the previous one, with one open PR per step.

## Requirements

Docker (with Compose), [uv](https://docs.astral.sh/uv/), Node 18+.

## Commands

| Command | What it does |
|---|---|
| `make seed` | Drop and recreate the database, run this checkout's migrations, load `funds.csv` |
| `make migrate` | Apply every migration up to this checkout (`alembic upgrade head`) |
| `make serve PORT=8001` | Run the API on that port (default 8000) |
| `make web API_PORT=8001` | Run the React dev server (http://localhost:5173) against the API on that port |

`DATABASE_URL` defaults to `postgresql://owl:owl@localhost:5432/owl`.

## Layout

- `app/` FastAPI app. All SQL lives in `app/funds_store.py` and names its columns explicitly.
- `migrations/` Alembic, with plain-SQL migrations (no ORM models).
- `web/` Vite + React.
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
