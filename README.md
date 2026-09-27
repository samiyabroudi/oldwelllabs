# OWL Full Stack Assessment

A small funds app (Postgres, FastAPI, React) used to demonstrate a zero-downtime,
rolling-deploy-safe migration of `funds.commitment` (text like `$1,200,000 USD`)
into `commitment_cents bigint` + `currency char(3)`.

Work lives on stacked step branches (`step-0-baseline` → `step-6-contract`),
each cut from the previous one, with one open PR per step.
