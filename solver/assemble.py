#!/usr/bin/env python3
"""Assemble + fully validate a submission CSV from a programs JSONL.

Gate checks (ALL must pass or no file is written):
  - every puzzle id in puzzles.csv is present exactly once, in order
  - every program replays VALID under validator.replay
  - every program: <= 4096 instructions and <= 131,072 bytes (compact JSON)
Output format matches the official sample: header id,program; program is a
compact-JSON list of [op, a, b, dest] with string ops.
Usage: assemble.py [programs.jsonl] [out.csv]
"""

import csv
import json
import sys

sys.path.insert(0, ".")
from validator import replay  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else "../submissions/programs_baseline.jsonl"
dst = sys.argv[2] if len(sys.argv) > 2 else "../submissions/submission_baseline.csv"

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

programs = {}
for line in open(src):
    rec = json.loads(line)
    if rec.get("program") is not None and rec.get("ok", True):
        programs[rec["id"]] = rec["program"]

problems = []
total = 0
for pid in order:
    if pid not in programs:
        problems.append(f"{pid}: missing")
        continue
    prog = programs[pid]
    ok, errs, n = replay(puzzles[pid], prog)
    if not ok:
        problems.append(f"{pid}: INVALID {errs[:1]}")
        continue
    blob = json.dumps(prog, separators=(",", ":"))
    if n > 4096:
        problems.append(f"{pid}: {n} instructions > 4096")
    if len(blob.encode()) > 131072:
        problems.append(f"{pid}: {len(blob.encode())} bytes > 131072")
    total += n

if problems:
    print(f"GATE FAILED: {len(problems)} problem(s); no file written")
    for p in problems[:10]:
        print(" ", p)
    sys.exit(1)

with open(dst, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "program"])
    for pid in order:
        w.writerow([pid, json.dumps(programs[pid], separators=(",", ":"))])
print(f"WROTE {dst}: 1000 programs, total instructions = {total}")
