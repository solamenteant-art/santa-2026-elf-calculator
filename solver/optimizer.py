#!/usr/bin/env python3
"""Post-pass optimizer for Santa 2026 programs (v1: dead-code elimination).

An instruction is DEAD when the value it writes is never read afterwards and
it is not the first production of a target (target coverage is sticky: once a
target value has appeared, it counts forever, even if overwritten later).
Liveness is computed on registers with last-writer tracking, which is sound:
a read always marks its actual last writer live, so removing dead writes can
never change what any surviving read sees. The result is re-validated with
validator.replay by the caller.
"""

import sys

sys.path.insert(0, ".")


def eliminate_dead(puzzle, prog):
    regs = [None] * 48
    for i, v in enumerate(puzzle["starts"]):
        regs[i] = v
    writer = [-1] * 48           # instruction index that wrote the current value
    src_writer = []              # per instruction: (writer of a, writer of b)
    first_prod = {}              # target value -> first instruction producing it
    targets = set(puzzle["targets"])
    for idx, (op, a, b, dest) in enumerate(prog):
        src_writer.append((writer[a], writer[b]))
        va, vb = regs[a], regs[b]
        if op == "+":
            r = va + vb
        elif op == "-":
            r = va - vb
        elif op == "*":
            r = va * vb
        else:
            r = va // vb
        if r in targets and r not in first_prod:
            first_prod[r] = idx
        regs[dest] = r
        writer[dest] = idx
    live = set(first_prod.values())
    for j in range(len(prog) - 1, -1, -1):
        if j in live:
            wa, wb = src_writer[j]
            if wa >= 0:
                live.add(wa)
            if wb >= 0:
                live.add(wb)
    return [ins for i, ins in enumerate(prog) if i in live]


if __name__ == "__main__":
    import csv
    import json

    from baseline import solve_puzzle
    from validator import replay

    path = sys.argv[1] if len(sys.argv) > 1 else "../data/practice_puzzles.csv"
    limit_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    rows = list(csv.DictReader(open(path)))
    before = after = 0
    bad = 0
    for row in rows[:limit_n]:
        p = {
            "starts": json.loads(row["starting_values"]),
            "targets": json.loads(row["targets"]),
            "value_limit": int(row["value_limit"]),
            "registers": int(row["registers"]),
        }
        prog = solve_puzzle(p)
        ok1, _, n1 = replay(p, prog)
        prog2 = eliminate_dead(p, prog)
        ok2, errs2, n2 = replay(p, prog2)
        if not (ok1 and ok2):
            bad += 1
            print(f"PROBLEM {row['id']}: base_ok={ok1} dce_ok={ok2} {errs2[:1]}")
            continue
        before += n1
        after += n2
    print(f"puzzles={limit_n} problems={bad}  before={before}  after_dce={after}  "
          f"saved={before - after} ({100.0 * (before - after) / max(before, 1):.1f}%)")
