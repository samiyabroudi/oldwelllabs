#!/usr/bin/env bash
# Replay a rolling deploy between two consecutive step branches.
#
#   scripts/replay.sh step_0 step_1
#   scripts/replay.sh --db-check step_2 step_3
#   scripts/replay.sh --code-first step_4 step_5
#
# Mirrors how the graders test: check out both branches side by side, point them at the
# same database, `make seed && make migrate` on the old one, `make migrate` on the new one,
# serve both, and check each one correctly reads what the other writes.
set -euo pipefail

# --db-check: after the API checks, also verify in SQL that every row's commitment_cents
# and currency agree with its commitment text. ONLY USEFUL FOR THE step_2 -> step_3 AND
# step_3 -> step_4 PAIRS. Before step 3 the new columns are legitimately NULL or stale
# (nothing has backfilled them yet); from step 5 the text column can be NULL and in step 6
# it's gone, so there is nothing to compare against. From step 4 on the API returns the
# new columns, so replay_check.py's consistency check already covers this without SQL.

# --code-first: skip `make migrate` on the new branch, so both versions serve against the
# OLD schema. Simulates the new code rolling out before its migration has run, to show
# which steps need their migration applied first. Expected: every pair passes except
# step_4 -> step_5, whose code inserts rows without the commitment text, which 0004's
# schema still requires (NOT NULL is only dropped by 0005).
DB_CHECK=0
CODE_FIRST=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --db-check) DB_CHECK=1 ;;
    --code-first) CODE_FIRST=1 ;;
    *) ARGS+=("$arg") ;;
  esac
done
USAGE="usage: replay.sh [--db-check] [--code-first] OLD_BRANCH NEW_BRANCH"
OLD=${ARGS[0]:?$USAGE}
NEW=${ARGS[1]:?$USAGE}
OLD_PORT=${OLD_PORT:-8101}
NEW_PORT=${NEW_PORT:-8102}

ROOT=$(git rev-parse --show-toplevel)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/owl-replay.XXXXXX")
PIDS=()

cleanup() {
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  git -C "$ROOT" worktree remove --force "$WORK/old" 2>/dev/null || true
  git -C "$ROOT" worktree remove --force "$WORK/new" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

step() { printf '\n==> %s\n' "$*"; }

wait_for() {
  for _ in $(seq 1 60); do
    curl -sf "http://localhost:$1/funds/1" >/dev/null && return 0
    sleep 0.5
  done
  echo "API on port $1 did not come up; log:" >&2
  cat "$WORK/serve-$1.log" >&2
  return 1
}

step "Checking out $OLD and $NEW"
git -C "$ROOT" worktree add --quiet --detach "$WORK/old" "$OLD"
git -C "$ROOT" worktree add --quiet --detach "$WORK/new" "$NEW"

step "[$OLD] make seed && make migrate"
make -C "$WORK/old" seed migrate

if [ "$CODE_FIRST" = 1 ]; then
  step "[$NEW] skipping make migrate (--code-first): both serve against $OLD's schema"
else
  step "[$NEW] make migrate"
  make -C "$WORK/new" migrate
fi

step "Serving $OLD on :$OLD_PORT and $NEW on :$NEW_PORT"
make -C "$WORK/old" serve PORT="$OLD_PORT" >"$WORK/serve-$OLD_PORT.log" 2>&1 &
PIDS+=($!)
make -C "$WORK/new" serve PORT="$NEW_PORT" >"$WORK/serve-$NEW_PORT.log" 2>&1 &
PIDS+=($!)
wait_for "$OLD_PORT"
wait_for "$NEW_PORT"

step "Cross-checking reads and writes"
python3 "$ROOT/scripts/replay_check.py" "http://localhost:$OLD_PORT" "http://localhost:$NEW_PORT"

if [ "$DB_CHECK" = 1 ]; then
  step "Checking every row's commitment_cents/currency against its text (--db-check)"
  # Same parsing as migration 0003. Any row returned is a mismatch.
  mismatches=$(docker compose -f "$ROOT/docker-compose.yml" exec -T db psql -U owl -d owl -tA -F ' | ' -c "
    SELECT id, commitment, commitment_cents, currency
      FROM funds
     WHERE commitment_cents IS DISTINCT FROM
             round(regexp_replace(commitment, '[^0-9.]', '', 'g')::numeric * 100)::bigint
        OR currency IS DISTINCT FROM right(btrim(commitment), 3)
     ORDER BY id")
  total=$(docker compose -f "$ROOT/docker-compose.yml" exec -T db psql -U owl -d owl -tA -c "SELECT count(*) FROM funds")
  if [ -n "$mismatches" ]; then
    echo "  FAIL  rows whose new columns disagree with commitment (id | commitment | cents | currency):"
    echo "$mismatches" | sed 's/^/          /'
    exit 1
  fi
  echo "  ok    all $total rows agree with their commitment text"
fi
