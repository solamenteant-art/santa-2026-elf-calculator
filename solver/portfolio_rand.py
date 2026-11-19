#!/usr/bin/env python3
"""Random-order portfolio pass: for each scored puzzle, re-solve under K
randomly shuffled target orders and keep the shortest VALID program,
starting from the incumbent (programs_dce.jsonl). Appends one JSON line
per puzzle (id, n, src, program) to ../submissions/programs_rand.jsonl,
flushed per puzzle. Resumable: ids already in the output are skipped.
Usage: portfolio_rand.py [start_idx] [end_idx] [K]"""

import csv
import json
import sys
import time

sys.path.insert(0, ".")
from baseline import solve_puzzle  # noqa: E402
from validator import replay  # noqa: E402

start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
end = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9
K = int(sys.argv[3]) if len(sys.argv) > 3 else 3
IN_PATH = sys.argv[4] if len(sys.argv) > 4 else "../submissions/programs_dce.jsonl"
OUT = sys.argv[5] if len(sys.argv) > 5 else "../submissions/programs_rand.jsonl"
SEED_BASE = int(sys.argv[6]) if len(sys.argv) > 6 else 0
MIN_LEN = int(sys.argv[7]) if len(sys.argv) > 7 else 0

rows = list(csv.DictReader(open("../data/puzzles.csv")))

incumbent = {}
for line in open(IN_PATH):
    r = json.loads(line)
    if r.get("program"):
        incumbent[r["id"]] = r["program"]

done_ids = set()
try:
    for line in open(OUT):
        done_ids.add(json.loads(line)["id"])
except FileNotFoundError:
    pass

out = open(OUT, "a")
saved_total = 0
for i, row in enumerate(rows):
    if i < start or i >= end or row["id"] in done_ids:
        continue
    if len(incumbent.get(row["id"], [])) < MIN_LEN:
        continue
    p = {
        "starts": json.loads(row["starting_values"]),
        "targets": json.loads(row["targets"]),
        "value_limit": int(row["value_limit"]),
        "registers": int(row["registers"]),
    }
    best = incumbent.get(row["id"])
    best_src = "in"
    best_n = len(best) if best else 10 ** 9
    t0 = time.time()
    for k in range(K):
        order = f"rand:{SEED_BASE + 1000 * i + k}"
        try:
            prog = solve_puzzle(p, order=order)
            ok, errs, n = replay(p, prog)
            if ok and n < best_n:
                best, best_src, best_n = prog, order, n
        except Exception as e:
            print(f"  {row['id']} {order} failed: {e}", flush=True)
    rec = {"id": row["id"], "n": best_n, "src": best_src,
           "secs": round(time.time() - t0, 2), "program": best}
    out.write(json.dumps(rec) + "\n")
    out.flush()
    base_n = len(incumbent[row["id"]]) if row["id"] in incumbent else -1
    saved = base_n - best_n
    saved_total += max(saved, 0)
    print(f"{i + 1}/1000 {row['id']} base={base_n} best={best_n} "
          f"src={best_src} saved={saved} {rec['secs']}s", flush=True)
out.close()
print(f"chunk done, total saved in chunk: {saved_total}", flush=True)
