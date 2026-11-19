#!/bin/bash
# Run one grind shard on this machine and push the results to the
# "shards" branch of the repo. Splits the puzzle range into PAR parallel
# portfolio_rand.py processes (the solver is single-threaded per puzzle).
#
# Env required: GITHUB_PAT (fine-grained, this repo only, contents write)
# Env optional: START END K SEED_BASE MIN_LEN PAR (defaults = proof burst)
set -u
START=${START:-0}
END=${END:-100}
K=${K:-10}
SEED_BASE=${SEED_BASE:-7000000}
MIN_LEN=${MIN_LEN:-400}
PAR=${PAR:-4}
REPO=${REPO:-solamenteant-art/santa-2026-elf-calculator}

cd "$(dirname "$0")/.." || exit 1
ROOT=$(pwd)
cat "$ROOT"/state/incumbent-*.jsonl > "$ROOT/state/incumbent.jsonl"
OUT="$ROOT/results/ec2-$SEED_BASE.jsonl"
mkdir -p "$ROOT/results"
rm -f "$OUT" "$OUT".part*

SPAN=$(( (END - START + PAR - 1) / PAR ))
pids=""
for i in $(seq 0 $((PAR - 1))); do
  s=$((START + i * SPAN))
  e=$((s + SPAN))
  [ "$e" -gt "$END" ] && e=$END
  [ "$s" -ge "$END" ] && break
  ( cd "$ROOT/solver" && python3 portfolio_rand.py "$s" "$e" "$K" \
      ../state/incumbent.jsonl "$OUT.part$i" $((SEED_BASE + i * 100000)) \
      "$MIN_LEN" ) &
  pids="$pids $!"
done
for p in $pids; do wait "$p"; done
cat "$OUT".part* > "$OUT" 2>/dev/null || true
rm -f "$OUT".part*
echo "shard rows: $(wc -l < "$OUT")"

if [ -n "${GITHUB_PAT:-}" ]; then
  git config user.name "elf-grind-ec2"
  git config user.email "elf-grind@localhost"
  git remote set-url origin "https://x-access-token:${GITHUB_PAT}@github.com/${REPO}.git"
  git fetch origin shards || true
  git checkout -B shards
  git add results/
  git commit -m "shard results: ec2 seed $SEED_BASE range $START-$END" || echo "nothing to commit"
  git push origin shards || echo "PUSH FAILED - results kept at $OUT"
else
  echo "no GITHUB_PAT set - results kept at $OUT"
fi
