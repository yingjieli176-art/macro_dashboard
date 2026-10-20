#!/usr/bin/env bash
# Called after a data-only commit. Rebase retries handle concurrent source jobs;
# a real content conflict fails visibly and is never resolved by overwriting it.
set -euo pipefail
for attempt in 1 2 3 4 5; do
  git fetch origin main
  if ! git rebase origin/main; then
    git rebase --abort
    echo 'Snapshot commit conflicts with newer upstream changes; preserving upstream.' >&2
    exit 1
  fi
  if git push origin HEAD:main; then
    exit 0
  fi
  if [ "$attempt" -lt 5 ]; then
    sleep "$attempt"
  fi
done
echo 'Snapshot push still rejected after five fetch/rebase attempts.' >&2
exit 1
