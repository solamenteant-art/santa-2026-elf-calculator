#!/usr/bin/env python3
"""Baseline constructive solver for Santa 2026 (v1).

Strategy per puzzle (targets processed in increasing order, one shared
register pool across the whole puzzle so intermediates are reused):
  0. If gcd(starts) = g > 1 and some target is not divisible by g, run the
     gcd escape: build g by batched Euclid, divide the starts by g, make 1.
  1. One-step: produce the target from two already-available values (+,-,*,/).
  2. Recursive build with the cheapest estimated strategy among:
     factor (v = d * (v/d) via Pollard-rho factorisation), double (v = v/2+v/2),
     predecessor (v = (v-1) + 1), overshoot (v = (v+1) - 1).
Every program is checked with validator.replay before it is counted.
"""

import json
import math
import random
import sys
from functools import lru_cache

sys.path.insert(0, ".")
from validator import replay  # noqa: E402

sys.setrecursionlimit(100000)

# ---------------- factoring: Miller-Rabin (det. < 2^64) + Pollard rho -------

def is_prime(n):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 325, 9375, 28178, 450775, 9780504, 1795265022):
        if a % n == 0:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _rho(n):
    if n % 2 == 0:
        return 2
    if n % 3 == 0:
        return 3
    while True:
        x = random.randrange(2, n)
        c = random.randrange(1, n)
        y, d = x, 1
        while d == 1:
            x = (x * x + c) % n
            y = (y * y + c) % n
            y = (y * y + c) % n
            d = math.gcd(abs(x - y), n)
        if d != n:
            return d


def factorize(n, out=None):
    if out is None:
        out = {}
    if n == 1:
        return out
    if is_prime(n):
        out[n] = out.get(n, 0) + 1
        return out
    d = _rho(n)
    factorize(d, out)
    factorize(n // d, out)
    return out


_DIV_CACHE = {}


def divisors(n):
    if n in _DIV_CACHE:
        return _DIV_CACHE[n]
    fac = factorize(n)
    divs = [1]
    for p, e in fac.items():
        divs = [d * p ** k for d in divs for k in range(e + 1)]
    out = sorted(divs)
    _DIV_CACHE[n] = out
    return out


# ---- small-value cost table: DP from {1} (1 counts as free), using +1 steps,
# ---- factor splits and doubling, then one backward overshoot pass.
_SMALL_N = 4096
_SMALL = [0] * (_SMALL_N + 3)
for _v in range(2, _SMALL_N + 2):
    _c = 1 + _SMALL[_v - 1]
    if _v % 2 == 0:
        _c = min(_c, 1 + _SMALL[_v // 2])
    _d = 2
    while _d * _d <= _v:
        if _v % _d == 0:
            _c = min(_c, 1 + _SMALL[_d] + _SMALL[_v // _d])
        _d += 1
    _SMALL[_v] = _c
for _v in range(_SMALL_N, 1, -1):
    _SMALL[_v] = min(_SMALL[_v], _SMALL[_v + 1] + 1)


# ---------------- the builder ------------------------------------------------

class CycleError(Exception):
    """Raised when build() re-enters a value already on the build stack
    (the pred/over ping-pong: v builds via v-1, v-1 builds via v+1 = v)."""


class Builder:
    def __init__(self, starts, targets, limit, order="asc"):
        self.limit = limit
        self.prog = []
        self.reg = {}
        self.regval = [None] * 48
        self.next_free = 0
        self.pinned = set(starts)
        self.protect = set()
        self._stack = set()
        self.recency = {}
        self.clock = 0
        tset = set(targets)
        if order == "desc":
            self.targets = sorted(tset, reverse=True)
        elif order == "bits":
            self.targets = sorted(
                tset, key=lambda v: (v.bit_length(), bin(v).count("1"), v))
        elif order.startswith("rand:"):
            self.targets = sorted(tset)
            random.Random(int(order[5:])).shuffle(self.targets)
        else:
            self.targets = sorted(tset)
        for i, v in enumerate(starts):
            self.reg[v] = i
            self.regval[i] = v
        self.next_free = len(starts)
        self._bc_memo = {}

    # -- register plumbing --
    def touch(self, v):
        self.clock += 1
        self.recency[v] = self.clock

    def alloc(self, v):
        if v in self.reg:
            return self.reg[v]
        if self.next_free < 48:
            r = self.next_free
            self.next_free += 1
        else:
            cands = [(self.recency.get(val, -1), val) for val in list(self.reg)
                     if val not in self.pinned and val not in self.protect]
            if not cands:  # last resort: evict the LRU protected value
                cands = [(self.recency.get(val, -1), val) for val in list(self.reg)
                         if val not in self.pinned]
            if not cands:
                raise RuntimeError("register exhaustion: everything pinned/protected")
            victim = min(cands)[1]
            r = self.reg.pop(victim)
        self.reg[v] = r
        self.regval[r] = v
        self.touch(v)
        return r

    def emit(self, op, x, y):
        rx, ry = self.reg[x], self.reg[y]
        if op == "+":
            r = x + y
        elif op == "-":
            r = x - y
        elif op == "*":
            r = x * y
        else:
            r = x // y
        assert 1 <= r <= self.limit, (op, x, y, r, self.limit)
        dest = self.alloc(r)
        self.prog.append([op, rx, ry, dest])
        self.touch(x)
        self.touch(y)
        return r

    # -- helpers --
    def have(self, v):
        return v in self.reg

    def ensure_one(self):
        if self.have(1):
            return
        s = next(iter(self.pinned))
        self.emit("/", s, s)

    def one_step(self, v):
        """Try to produce v in exactly one instruction from available values."""
        avail = list(self.reg.keys())
        for x in avail:
            if v - x > 0 and self.have(v - x):
                self.emit("+", x, v - x)
                return True
            if x > v and self.have(x - v):
                self.emit("-", x, x - v)
                return True
            if v % x == 0 and self.have(v // x):
                self.emit("*", x, v // x)
                return True
            if x % v == 0 and v != 0 and self.have(x // v) and x // v != 0:
                self.emit("/", x, x // v)
                return True
            if v * x <= self.limit and self.have(v * x):
                self.emit("/", v * x, x)
                return True
        return False

    def base_cost(self, v, depth=0):
        """Estimated instructions to build v: factor/double driven, with the
        small-value DP table below 4096 and the binary method as a cap."""
        if v in self.reg:
            return 0
        if v == 1:
            return 1
        if v <= _SMALL_N:
            return _SMALL[v] + (0 if self.have(1) else 1)
        if depth > 70:
            return v.bit_length() + bin(v).count("1")
        if v in self._bc_memo:
            return self._bc_memo[v]
        best = v.bit_length() + bin(v).count("1")  # binary method from 1
        if v % 2 == 0:
            best = min(best, 1 + self.base_cost(v // 2, depth + 1))
        if not is_prime(v):
            for d in divisors(v):
                if 1 < d < v and d <= v // d:
                    c = 1 + self.base_cost(d, depth + 1) + self.base_cost(v // d, depth + 1)
                    if c < best:
                        best = c
        self._bc_memo[v] = best
        return best

    def base_option(self, v):
        """Bos-Coster style: v = q*b + r (or (q+1)*b - r2) around an available
        base b. Returns (cost, (b, q, r, mode)) or None. mode '+' uses q*b + r;
        mode '-' uses (q+1)*b - r2; r == 0 means a pure multiply."""
        bases = set(self.pinned)
        bases.update(sorted(self.reg.keys(), reverse=True)[:10])
        best = None
        for b in bases:
            if b <= 1 or b >= v:
                continue
            q, r = divmod(v, b)
            if q < 1:
                continue
            c = self.base_cost(q) + (self.base_cost(r) if r else 0) + (2 if r else 1)
            if best is None or c < best[0]:
                best = (c, (b, q, r, "+"))
            r2 = (q + 1) * b - v
            if 0 < r2 < b and (q + 1) * b <= self.limit:
                c2 = self.base_cost(q + 1) + self.base_cost(r2) + 2
                if c2 < best[0]:
                    best = (c2, (b, q + 1, r2, "-"))
        return best

    def est(self, v):
        """Estimated extra instructions to build v from the current pool:
        the best of pure factor/double, or one pred/over step on top of it."""
        if v in self.reg:
            return 0
        if v == 1:
            return 1
        best = self.base_cost(v)
        if v - 1 >= 1:
            best = min(best, 2 + self.base_cost(v - 1))
        if v + 1 <= self.limit:
            best = min(best, 2 + self.base_cost(v + 1))
        bo = self.base_option(v)
        if bo is not None:
            best = min(best, bo[0])
        return best

    def build(self, v):
        if self.have(v):
            return
        if len(self.prog) > 3900:
            raise RuntimeError("instruction budget exceeded")
        if v == 1:
            self.ensure_one()
            return
        if v in self._stack:
            raise CycleError(v)
        if self.one_step(v):
            return
        # choose strategy by estimate (factor/double via base_cost, else pred/over)
        options = []
        bc = self.base_cost(v)
        if bc < 10 ** 9:
            if v % 2 == 0 and 1 + self.base_cost(v // 2) == bc:
                options.append((bc, "double", (v // 2,)))
            else:
                for d in divisors(v):
                    if 1 < d < v and d <= v // d and \
                            1 + self.base_cost(d) + self.base_cost(v // d) == bc:
                        options.append((bc, "factor", (d, v // d)))
                        break
        if v - 1 >= 1:
            options.append((2 + self.base_cost(v - 1), "pred", (v - 1,)))
        if v + 1 <= self.limit:
            options.append((2 + self.base_cost(v + 1), "over", (v + 1,)))
        bo = self.base_option(v)
        if bo is not None:
            options.append((bo[0], "base", bo[1]))
        if not options:  # all estimates inf: strictly-decreasing fallback
            if v % 2 == 0:
                options.append((0, "double", (v // 2,)))
            elif v - 1 >= 2:
                options.append((0, "pred", (v - 1,)))
            else:
                options.append((0, "over", (v + 1,)))
        options.sort(key=lambda t: t[0])
        self._stack.add(v)
        try:
            last_err = None
            for _, kind, args in options:
                try:
                    self._execute(kind, args)
                    return
                except CycleError as e:
                    last_err = e
                    continue
            raise RuntimeError(f"all strategies cycled for {v}") from last_err
        finally:
            self._stack.discard(v)

    def _execute(self, kind, args):
        if kind == "double":
            self.build(args[0])
            self.protect.add(args[0])
            self.emit("+", args[0], args[0])
            self.protect.discard(args[0])
        elif kind == "factor":
            self.build(args[0])
            self.protect.add(args[0])
            self.build(args[1])
            if not self.have(args[0]):
                self.build(args[0])
            if not self.have(args[1]):
                self.build(args[1])
            self.emit("*", args[0], args[1])
            self.protect.discard(args[0])
        elif kind == "pred":
            self.build(args[0])
            self.protect.add(args[0])
            self.ensure_one()
            self.emit("+", args[0], 1)
            self.protect.discard(args[0])
        elif kind == "over":
            self.build(args[0])
            self.protect.add(args[0])
            self.ensure_one()
            self.emit("-", args[0], 1)
            self.protect.discard(args[0])
        else:  # base decomposition around an available base b
            b, q, r, mode = args
            self.protect.add(b)
            self.build(q)
            self.protect.add(q)
            if r:
                self.build(r)
                self.protect.add(r)
                if not self.have(q):
                    self.build(q)
            qb = self.emit("*", q, b)
            if r:
                self.protect.add(qb)
                if not self.have(r):
                    self.build(r)
                self.emit("+" if mode == "+" else "-", qb, r)
                self.protect.discard(qb)
                self.protect.discard(r)
            self.protect.discard(q)
            self.protect.discard(b)

    # -- gcd escape --
    def _sub_multiple(self, x, y):
        """Return value x mod y (x, y available, x > y), via batched doubling."""
        q = x // y
        if q == 0:
            return x
        acc = None
        base = y
        bit = 1
        qq = q
        while qq:
            if qq & 1:
                acc = base if acc is None else self.emit("+", acc, base)
            qq >>= 1
            if qq:
                base = self.emit("+", base, base)
        if acc == x:
            return 0
        return self.emit("-", x, acc)

    def gcd_escape(self):
        starts = sorted(self.pinned)
        g = 0
        for s in starts:
            g = math.gcd(g, s)
        if g <= 1:
            return
        if all(t % g == 0 for t in self.targets):
            return
        # Euclid on the two smallest starts, batched.
        a, b = starts[0], starts[1] if len(starts) > 1 else starts[0]
        x, y = max(a, b), min(a, b)
        while y != 0 and x != y:
            r = self._sub_multiple(x, y) if x > y else self._sub_multiple(y, x)
            if r == 0:
                break
            x, y = (y, r) if y > r else (r, y)
            if x < y:
                x, y = y, x
        # gcd value g should now be available if Euclid landed on it; if not,
        # fall back: divide a start by (start/g) built recursively.
        if not self.have(g):
            s = starts[0]
            self.build(s // g)
            self.emit("/", s, s // g)  # now g is available
        for s in starts:
            if s % g == 0 and not self.have(s // g):
                self.emit("/", s, g)
        self.ensure_one()

    # -- main --
    def solve(self):
        self.gcd_escape()
        for t in self.targets:
            self.protect = set()
            self._bc_memo = {}
            if not self.have(t):
                self.build(t)
        return self.prog


def solve_puzzle(p, order="asc"):
    # Seed Pollard-rho per puzzle so every result is reproducible.
    random.seed(hash((tuple(p["starts"]), tuple(p["targets"]), order)) & 0xFFFFFFFF)
    b = Builder(p["starts"], p["targets"], p["value_limit"], order=order)
    prog = b.solve()
    return prog


if __name__ == "__main__":
    import csv

    path = sys.argv[1] if len(sys.argv) > 1 else "../data/practice_puzzles.csv"
    limit_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9
    rows = list(csv.DictReader(open(path)))
    total = 0
    lb_total = 0
    fails = []
    by_family = {}
    for i, row in enumerate(rows[:limit_n]):
        p = {
            "starts": json.loads(row["starting_values"]),
            "targets": json.loads(row["targets"]),
            "value_limit": int(row["value_limit"]),
            "registers": int(row["registers"]),
        }
        try:
            prog = solve_puzzle(p)
            ok, errs, n = replay(p, prog)
        except Exception as e:
            ok, errs, n = False, [f"exception: {e}"], -1
        lb = int(row["lower_bound"]) if "lower_bound" in row else 0
        lb_total += lb
        fam = row.get("family", "?")
        d = by_family.setdefault(fam, [0, 0, 0])
        d[1] += lb
        d[2] += 1
        if ok:
            total += n
            d[0] += n
        else:
            fails.append((row["id"], errs[:2]))
            print(f"FAIL {row['id']} ({fam}): {errs[:2]}")
    print(f"\npuzzles: {min(limit_n, len(rows))}  solved-ok: {min(limit_n, len(rows)) - len(fails)}  failed: {len(fails)}")
    print(f"total instructions: {total}   sum lower_bound: {lb_total}   ratio: {total / max(lb_total,1):.2f}x")
    for fam, (tot, lb, cnt) in sorted(by_family.items()):
        print(f"  {fam:15s} n={cnt:3d}  instr={tot:7d}  lb={lb:5d}  ratio={tot / max(lb,1):.2f}x")
