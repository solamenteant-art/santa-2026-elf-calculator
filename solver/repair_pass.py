#!/usr/bin/env python3
"""Batch tear-out-and-rebuild repair over a programs JSONL.

For each puzzle in [start, end): run repair.repair_program on the
incumbent program with a per-puzzle seconds budget, replay-validate,
and append (id, n, src, program) with the best valid program found
(never worse than the incumbent). Resumable by id.
Usage: repair_pass.py [in.jsonl] [out.jsonl] [start] [end] [secs] [seed_base]
"""

import csv
import json
import sys
import time

sys.path.insert(0, ".")
from repair import repair_program  # noqa: E402
from validator import replay  # noqa: E402

in_path = sys.argv[1] if len(sys.argv) > 1 else "../submissions/programs_best_dce.jsonl"
out_path = sys.argv[2] if len(sys.argv) > 2 else "../submissions/programs_repair.jsonl"
start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
end = int(sys.argv[4]) if len(sys.argv) > 4 else 10 ** 9
secs = float(sys.argv[5]) if len(sys.argv) > 5 else 30.0
seed_base = int(sys.argv[6]) if len(sys.argv) > 6 else 7700000

puzzles = {}
order = []
for row in csv.DictReader(open("../data/puzzles.csv")):
    puzzles[row["id"]] = {
        "starts": json.loads(row["starting_values"]),
        "targets": json.loads(row["targets"]),
        "value_limit": int(row["value_limit"]),
        "registers": int(row["registers"]),
    }
    order.append(row["id"])

incumbent = {}
for line in open(in_path):
    r = json.loads(line)
    incumbent[r["id"]] = r

done = set()
try:
    for line in open(out_path):
        done.add(json.loads(line)["id"])
except FileNotFoundError:
    pass

out = open(out_path, "a")
total_in = total_out = 0
for idx, pid in enumerate(order):
    if idx < start or idx >= end or pid in done or pid not in incumbent:
        continue
    p = puzzles[pid]
    prog = incumbent[pid]["program"]
    t0 = time.time()
    best = repair_program(p, prog, seconds=secs, seed=seed_base + idx)
    ok, _, n = replay(p, best)
    if not ok or n > len(prog):
        best, n = prog, len(prog)
    total_in += len(prog)
    total_out += n
    out.write(json.dumps({"id": pid, "n": n, "src": "repair",
                          "program": best}) + "\n")
    out.flush()
    print(f"{idx + 1}/1000 {pid} in={len(prog)} best={n} "
          f"saved={len(prog) - n} {time.time() - t0:.1f}s", flush=True)
print(f"repair pass done: in={total_in} out={total_out} "
      f"saved={total_in - total_out}")
