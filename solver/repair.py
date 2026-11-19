#!/usr/bin/env python3
"""Tear-out-and-rebuild repair for Santa 2026 programs (math audit item 3).

Works at the VALUE level. A program induces an ordered chain of distinct
produced values, each with a derivation (op, a, b) from earlier values.
One repair attempt:

  1. pick a contiguous window of the chain,
  2. tear it out — the values the rest of the program still needs from
     the window (targets, or operands of later derivations) are its
     EXPORTS,
  3. rebuild the exports from the surviving earlier values (the
     ANCHORS) with the constructive builder, on a synthetic puzzle,
  4. if the rebuilt segment is shorter, splice it in, re-emit the whole
     chain through a 48-register Belady allocator, and let
     validator.replay judge the result. Only validated, shorter
     programs are ever kept.

DCE (optimizer.eliminate_dead) can only delete waste; this pass can
REPLACE a bad shared sub-chain with a better one, which is the move the
literature (Bahig et al. 2024, simulated annealing on addition
sequences) endorses. v1 acceptance is greedy over random windows
(random-restart local search); temperature acceptance is a later
refinement.
"""

import random
import sys

sys.path.insert(0, ".")
from baseline import solve_puzzle  # noqa: E402
from validator import replay  # noqa: E402

OPS = {"+": lambda a, b: a + b, "-": lambda a, b: a - b,
       "*": lambda a, b: a * b, "/": lambda a, b: a // b}


def trace_chain(puzzle, prog):
    """Program -> ordered [(value, op, a_val, b_val)] of distinct produced
    values (starts excluded), or None if the program is malformed."""
    regs = [None] * 48
    for i, v in enumerate(puzzle["starts"]):
        regs[i] = v
    seen = set(puzzle["starts"])
    chain = []
    for op, a, b, dest in prog:
        va, vb = regs[a], regs[b]
        if va is None or vb is None:
            return None
        r = OPS[op](va, vb)
        regs[dest] = r
        if r not in seen:
            seen.add(r)
            chain.append((r, op, va, vb))
    return chain


def chain_to_values(chain):
    return [c[0] for c in chain]


def emit(puzzle, chain):
    """Chain -> program via a 48-register allocator (Belady eviction:
    evict the value whose next use is farthest away; the current step's
    operands are protected). Returns None if an operand was evicted
    before its use — validator.replay is the final judge regardless."""
    nreg = puzzle["registers"]
    starts = list(puzzle["starts"])
    if len(starts) > nreg:
        return None
    # next-use positions for every value
    uses = {}
    for idx, (_, _, va, vb) in enumerate(chain):
        uses.setdefault(va, []).append(idx)
        uses.setdefault(vb, []).append(idx)
    for v in puzzle["targets"]:
        uses.setdefault(v, []).append(len(chain))  # targets stay live
    reg_of = {}
    regs = [None] * nreg
    for i, v in enumerate(starts):
        regs[i] = v
        reg_of[v] = i
    free = list(range(len(starts), nreg))
    prog = []

    def next_use(v, after):
        for u in uses.get(v, []):
            if u > after:
                return u
        return 1 << 62

    for idx, (val, op, va, vb) in enumerate(chain):
        if va not in reg_of or vb not in reg_of:
            return None
        if val in reg_of:
            continue  # already available (duplicate production)
        if free:
            dest = free.pop()
        else:
            cand = None
            far = -1
            for v, r in reg_of.items():
                if v == va or v == vb:
                    continue
                nu = next_use(v, idx)
                if nu > far:
                    far, cand = nu, v
            if cand is None:
                return None
            dest = reg_of.pop(cand)
            regs[dest] = None
        prog.append([op, reg_of[va], reg_of[vb], dest])
        regs[dest] = val
        reg_of[val] = dest
    return prog


def _exports(chain, i, j, targets):
    window_vals = {c[0] for c in chain[i:j]}
    used_later = set()
    for _, _, va, vb in chain[j:]:
        used_later.add(va)
        used_later.add(vb)
    return [c[0] for c in chain[i:j]
            if c[0] in targets or c[0] in used_later]


def _anchors(puzzle, chain, i, j):
    """Values available before the window that a rebuild may use:
    everything used at or after the window, all starts, and the largest
    earlier values (stepping-stone bases). Capped so the synthetic
    puzzle fits the register model."""
    used = set(puzzle["starts"])
    for _, _, va, vb in chain[i:]:
        used.add(va)
        used.add(vb)
    anchors = [c[0] for c in chain[:i] if c[0] in used]
    big = sorted((c[0] for c in chain[:i] if c[0] not in used),
                 reverse=True)
    anchors.extend(big[: max(0, 44 - len(anchors))])
    return anchors[:44]


def attempt_repair(puzzle, chain, rng):
    """One random window tear-out/rebuild. Returns a new chain or None."""
    m = len(chain)
    if m < 12:
        return None
    targets = set(puzzle["targets"])
    size = rng.randint(5, min(40, m - 1))
    i = rng.randint(0, m - size)
    j = i + size
    exports = _exports(chain, i, j, targets)
    if not exports:
        return chain[:i] + chain[j:]  # pure dead segment: free win
    anchors = _anchors(puzzle, chain, i, j)
    if not anchors:
        return None
    synth = {
        "starts": anchors,
        "targets": exports,
        "value_limit": puzzle["value_limit"],
        "registers": puzzle["registers"],
    }
    try:
        prog = solve_puzzle(synth, order="asc")
    except Exception:
        return None
    ok, _, _ = replay(synth, prog)
    if not ok:
        return None
    sub = trace_chain(synth, prog)
    if sub is None:
        return None
    produced = {c[0] for c in sub}
    if not set(exports) <= produced:
        return None
    if len(sub) >= size:
        return None  # rebuild must actually be shorter
    return chain[:i] + sub + chain[j:]


def repair_program(puzzle, prog, seconds=30.0, seed=0, max_attempts=200):
    """Random-restart window repair. Returns the best VALID program
    found (never worse than the input)."""
    import time

    from optimizer import eliminate_dead

    rng = random.Random(seed)
    chain = trace_chain(puzzle, prog)
    if chain is None:
        return prog
    best_prog = prog
    best_len = len(prog)
    t0 = time.time()
    attempts = 0
    while time.time() - t0 < seconds and attempts < max_attempts:
        attempts += 1
        cand_chain = attempt_repair(puzzle, chain, rng)
        if cand_chain is None:
            continue
        cand = emit(puzzle, cand_chain)
        if cand is None:
            continue
        ok, _, n = replay(puzzle, cand)
        if not ok:
            continue
        cand = eliminate_dead(puzzle, cand)
        ok, _, n = replay(puzzle, cand)
        if ok and n < best_len:
            best_prog, best_len = cand, n
            chain = trace_chain(puzzle, cand) or chain
    return best_prog
