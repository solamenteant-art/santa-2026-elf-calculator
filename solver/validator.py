#!/usr/bin/env python3
"""Replay validator for Kaggle Santa 2026 - The Elf Calculator.

Built ONLY from the official Data page descriptions (read live 2026-11-18):
- puzzles.csv columns: id, starting_values (JSON array; occupy registers
  0..len-1 at start), targets (JSON array, increasing; program must produce
  each at least once), value_limit (largest value allowed in any register
  during execution), registers (48 for every puzzle).
- Submission CSV: id, program. One row per scored puzzle.
- If ANY program is invalid, the whole submission is rejected (Overview).

Calculator semantics (Overview/Data + worked example example_0001):
- Instruction: [op, a, b, dest]; op in + - * / ; a, b, dest are register
  indices 0..47. Reading an undefined register is invalid.
- Subtraction only when a > b (result stays positive).
- Division only when exact (a % b == 0, b != 0).
- Every result must be <= value_limit (and >= 1).
- A target counts once it has been produced at least once during the run,
  even if its register is later overwritten.
- Limits per program: <= 4096 instructions, <= 131072 bytes in the CSV cell.

OP ENCODING: the sample file's encoding is confirmed by fingerprint against
the published op census of the sample submission (additions 1,462,481;
multiplications 26,898; divisions 1,000; subtractions 0; total 1,490,379).
String ops are accepted directly; integer op codes are tried under candidate
mappings by check_sample_encoding() and the mapping is only trusted if the
census AND the total match exactly.
"""

import csv
import json
import sys
from collections import Counter

MAX_INSTR = 4096
MAX_CELL_BYTES = 131072
NREG = 48

SAMPLE_CENSUS = {"+": 1462481, "*": 26898, "/": 1000, "-": 0}
SAMPLE_TOTAL = 1490379

INT_MAP_CANDIDATES = [
    {0: "+", 1: "-", 2: "*", 3: "/"},
    {0: "+", 1: "*", 2: "-", 3: "/"},
    {0: "+", 1: "-", 2: "/", 3: "*"},
    {0: "+", 1: "*", 2: "/", 3: "-"},
    {0: "+", 1: "/", 2: "*", 3: "-"},
    {0: "+", 1: "/", 2: "-", 3: "*"},
]


def load_puzzles(path):
    puzzles = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            puzzles[row["id"]] = {
                "starts": json.loads(row["starting_values"]),
                "targets": json.loads(row["targets"]),
                "value_limit": int(row["value_limit"]),
                "registers": int(row["registers"]),
            }
    return puzzles


def replay(puzzle, program, opmap=None):
    """Return (ok, errors, length). Program is a parsed JSON list."""
    errors = []
    if not isinstance(program, list):
        return False, ["program is not a list"], 0
    if len(program) > MAX_INSTR:
        errors.append(f"too many instructions: {len(program)} > {MAX_INSTR}")
    regs = [None] * NREG
    for i, v in enumerate(puzzle["starts"]):
        regs[i] = v
    produced = set(v for v in puzzle["starts"])
    limit = puzzle["value_limit"]
    for pc, ins in enumerate(program):
        if not isinstance(ins, (list, tuple)) or len(ins) != 4:
            errors.append(f"instr {pc}: not a 4-element list: {ins!r}")
            return False, errors, len(program)
        op, a, b, dest = ins
        if isinstance(op, int):
            if opmap is None or op not in opmap:
                errors.append(f"instr {pc}: unmapped int op {op!r}")
                return False, errors, len(program)
            op = opmap[op]
        if op not in "+-*/":
            errors.append(f"instr {pc}: bad op {op!r}")
            return False, errors, len(program)
        if not all(isinstance(x, int) and 0 <= x < NREG for x in (a, b, dest)):
            errors.append(f"instr {pc}: register index out of range: {ins!r}")
            return False, errors, len(program)
        va, vb = regs[a], regs[b]
        if va is None or vb is None:
            errors.append(f"instr {pc}: read of undefined register ({a}={va}, {b}={vb})")
            return False, errors, len(program)
        if op == "+":
            r = va + vb
        elif op == "-":
            if not va > vb:
                errors.append(f"instr {pc}: subtraction not positive: {va} - {vb}")
                return False, errors, len(program)
            r = va - vb
        elif op == "*":
            r = va * vb
        else:  # "/"
            if vb == 0 or va % vb != 0:
                errors.append(f"instr {pc}: inexact division: {va} / {vb}")
                return False, errors, len(program)
            r = va // vb
        if r < 1 or r > limit:
            errors.append(f"instr {pc}: result {r} outside 1..{limit}")
            return False, errors, len(program)
        regs[dest] = r
        produced.add(r)
    missing = [t for t in puzzle["targets"] if t not in produced]
    if missing:
        errors.append(f"targets never produced: {missing[:5]}{'...' if len(missing) > 5 else ''} ({len(missing)} missing)")
    return not errors, errors, len(program)


def iter_submission(path):
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            yield row["id"], row["program"]


def census_and_total(submission_path, opmap=None):
    census = Counter()
    total = 0
    for _pid, cell in iter_submission(submission_path):
        prog = json.loads(cell)
        total += len(prog)
        for ins in prog:
            op = ins[0]
            if isinstance(op, int):
                op = opmap[op] if opmap and op in opmap else op
            census[op] += 1
    return census, total


def check_sample_encoding(sample_path):
    """Tripwire: find the op encoding that reproduces the published census
    and total of the official sample submission EXACTLY. Returns opmap or None."""
    # String-op case first.
    census, total = census_and_total(sample_path)
    if total == SAMPLE_TOTAL and all(census[k] == v for k, v in SAMPLE_CENSUS.items()):
        return {}
    for cand in INT_MAP_CANDIDATES:
        census, total = census_and_total(sample_path, cand)
        if total == SAMPLE_TOTAL and all(census[k] == v for k, v in SAMPLE_CENSUS.items()):
            return cand
    return None


def validate_submission(puzzles, submission_path, opmap=None):
    """Full-file validation. Returns (ok, total_score, problems list)."""
    problems = []
    seen = set()
    total = 0
    with open(submission_path, newline="") as f:
        for row in csv.DictReader(f):
            pid, cell = row["id"], row["program"]
            if pid in seen:
                problems.append(f"{pid}: duplicate row")
                continue
            seen.add(pid)
            if pid not in puzzles:
                problems.append(f"{pid}: not a scored puzzle id")
                continue
            if len(cell.encode()) > MAX_CELL_BYTES:
                problems.append(f"{pid}: cell too large ({len(cell.encode())} bytes)")
                continue
            try:
                prog = json.loads(cell)
            except Exception as e:
                problems.append(f"{pid}: program JSON unparseable: {e}")
                continue
            ok, errs, length = replay(puzzles[pid], prog, opmap)
            if not ok:
                problems.append(f"{pid}: " + "; ".join(errs[:3]))
            total += length
    missing = set(puzzles) - seen
    if missing:
        problems.append(f"missing rows for {len(missing)} puzzles, e.g. {sorted(missing)[:5]}")
    return not problems, total, problems


if __name__ == "__main__":
    # Worked example from the official Overview (example_0001):
    # starts [3], targets [1,2,5,8], limit 9 -> 4 instructions:
    # 3/3=1, 3-1=2, 3+2=5, 3+5=8 (registers: 0=3; write 1->r1, 2->r2, 5->r3, 8->r4)
    ex = {"starts": [3], "targets": [1, 2, 5, 8], "value_limit": 9, "registers": 48}
    prog = [["/", 0, 0, 1], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4]]
    ok, errs, n = replay(ex, prog)
    print("worked example:", "OK" if ok else f"FAIL {errs}", "length", n)
    assert ok and n == 4
    print("validator self-test passed")
