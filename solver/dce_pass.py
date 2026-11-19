#!/usr/bin/env python3
"""Dead-code elimination pass over a programs JSONL: for each puzzle, run
optimizer.eliminate_dead on the incumbent program, replay-validate, and
keep the shorter valid program. Appends (id, n, src, program) lines to the
output JSONL; resumable by id.
Usage: dce_pass.py [in.jsonl] [out.jsonl] [start_idx] [end_idx]"""

import csv
import json
import sys
import time

sys.path.insert(0, ".")
from optimizer import eliminate_dead  # noqa: E402
from validator import replay  # noqa: E402

src_path = sys.argv[1] if len(sys.argv) > 1 else "../submissions/programs_portfolio.jsonl"
out_path = sys.argv[2] if len(sys.argv) > 2 else "../submissions/programs_dce.jsonl"
start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
end = int(sys.argv[4]) if len(sys.argv) > 4 else 10 ** 9

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
for line in open(src_path):
    r = json.loads(line)
    if r.get("program"):
        incumbent[r["id"]] = r["program"]

done_ids = set()
try:
    for line in open(out_path):
        done_ids.add(json.loads(line)["id"])
except FileNotFoundError:
    pass

out = open(out_path, "a")
saved_total = 0
for i, pid in enumerate(order):
    if i < start or i >= end or pid in done_ids or pid not in incumbent:
        continue
    p = puzzles[pid]
    prog = incumbent[pid]
    best, best_src = prog, "in"
    t0 = time.time()
    try:
        cand = eliminate_dead(p, prog)
        if len(cand) < len(prog):
            ok, errs, n = replay(p, cand)
            if ok:
                best, best_src = cand, "dce"
    except Exception as e:
        print(f"  {pid} dce failed: {e}", flush=True)
    rec = {"id": pid, "n": len(best), "src": best_src, "program": best}
    out.write(json.dumps(rec) + "\n")
    out.flush()
    saved = len(prog) - len(best)
    saved_total += saved
    print(f"{i + 1}/1000 {pid} in={len(prog)} best={len(best)} src={best_src} "
          f"saved={saved} {round(time.time() - t0, 2)}s", flush=True)
out.close()
print(f"chunk done, total saved in chunk: {saved_total}", flush=True)
