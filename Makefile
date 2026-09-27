PORT ?= 8000
DATABASE_URL ?= postgresql://owl:owl@localhost:5432/owl
export DATABASE_URL

.PHONY: db seed migrate serve

# Start Postgres and wait until it accepts connections.
db:
	docker compose up -d --wait db

# Drop and recreate the database, migrate it to this checkout, load funds.csv.
seed: db
	uv run python -m app.seed

# Apply every migration up to this checkout.
migrate: db
	uv run alembic upgrade head

# Run the API, e.g. `make serve PORT=8001`.
serve:
	uv run uvicorn app.main:app --port $(PORT)
