#!/usr/bin/env bash
# Replay a rolling deploy between two consecutive step branches.
#
#   scripts/replay.sh step_0 step_1
#
# Mirrors how the graders test: check out both branches side by side, point them at the
# same database, `make seed && make migrate` on the old one, `make migrate` on the new one,
# serve both, and check each one correctly reads what the other writes.
set -euo pipefail

OLD=${1:?usage: replay.sh OLD_BRANCH NEW_BRANCH}
NEW=${2:?usage: replay.sh OLD_BRANCH NEW_BRANCH}
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

step "[$NEW] make migrate"
make -C "$WORK/new" migrate

step "Serving $OLD on :$OLD_PORT and $NEW on :$NEW_PORT"
make -C "$WORK/old" serve PORT="$OLD_PORT" >"$WORK/serve-$OLD_PORT.log" 2>&1 &
PIDS+=($!)
make -C "$WORK/new" serve PORT="$NEW_PORT" >"$WORK/serve-$NEW_PORT.log" 2>&1 &
PIDS+=($!)
wait_for "$OLD_PORT"
wait_for "$NEW_PORT"

step "Cross-checking reads and writes"
python3 "$ROOT/scripts/replay_check.py" "http://localhost:$OLD_PORT" "http://localhost:$NEW_PORT"
