# Santa 2026 — The Elf Calculator: solver

Entry of **Antonio Arroyo Diaz** in Kaggle's *Santa 2026 — The Elf
Calculator*. The task: for each of 1,000 puzzles, write the shortest
possible arithmetic program (only `+  −  ×  ÷`, 48 registers) that
produces every target number from the given starting values, never
breaking the rules (subtraction only when the result stays positive,
division only when it comes out exact, no intermediate above the
puzzle's value limit). The score is the total instruction count across
all 1,000 programs — lower is better.

## Method, in plain language

Each puzzle is solved by a builder that grows a shared pool of useful
numbers: every new value is computed once and can feed every remaining
target. The builder tries several ways to reach each target — one step
from a pool value, factoring, doubling, building a near neighbour and
adjusting, overshooting and coming back, splitting a target over a
convenient base (`v = q·b ± r`), and a gcd escape when nothing else
fits. On top of the builder sit three layers:

1. **Portfolios** — the same puzzle is re-solved under many different
   target orders (ascending, descending, by bit length, and randomized
   shuffles); the shortest valid program wins.
2. **Dead-code elimination** — a liveness pass deletes instructions
   whose results nothing later uses.
3. **A gated assembler** — before any submission file is written, every
   one of the 1,000 programs is replayed through an independent
   validator and checked against the size caps. One invalid program
   would kill the whole submission, so nothing ships unproven.

The problem is a cousin of the classical *addition sequence* problem,
which is NP-complete — nobody can certify a perfect answer at this
scale, so the work is a long, checkpointed grind: many machines solve
independent slices and the results merge by "shortest valid program
per puzzle."

## Layout

- `solver/` — validator, constructive builder, optimizer, portfolio
  drivers, gated assembler (pure Python standard library, no installs)
- `data/puzzles.csv` — the competition puzzles
- `state/incumbent-*.jsonl` — the best program found so far per puzzle
  (split into parts; concatenate into `state/incumbent.jsonl` to use)
- `jobs/` — shard job specs; pushing one starts a grind shard
- `results/` — shard outputs land here on the `shards` branch

## Verification

`solver/validator.py` replays the official worked example correctly,
and a census replay of the official sample submission reproduces its
published operation counts exactly (+1,462,481 · ×26,898 · ÷1,000 ·
−0 · total 1,490,379), which pins the rule semantics down before any
of our own programs are trusted.
