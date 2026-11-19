# AWS burst plan — staged, modest, nothing idle

Credits: $1,100 total on the MeeVerse Engine LLC account. Allocation
(Antonio's ruling, Nov 19, 2026): **smart split** — Kaggle's November
CPU work stays small (~$50 working cap), the voice-clone retrain keeps
its share (planned Sat Nov 21), and the bulk is preserved for
December's GPU phase.

## Stage 1 — proof burst (a few dollars)

- One **c7i.2xlarge Spot** instance, region **us-west-2 (Oregon)** —
  closest region, deep spot capacity; ~$0.11–0.14/hr spot.
- `user_data.sh` bootstrap: clone this repo, run one 100-puzzle shard
  (seed base 7000000, 4 parallel workers), push results to the
  `shards` branch, **shut itself down**. Total expected cost: under
  $0.50.
- Proves the whole loop: launch → grind → results back → merge here.
- Spot-interruption safety: shards are checkpointed and merged by
  "shortest valid program per puzzle," so an interruption loses at
  most the in-flight puzzle attempts — never correctness, never
  banked work.

## Stage 2 — November CPU slice (after proof passes)

- A handful of spot instances on wider/heavier slices (heaviest
  puzzles first — the top 200 carry a third of the total score).
- Every stage reports its credit cost before the next one launches.

## Stage 3 — December GPU phase (the bulk of the credits)

- GPU/CUDA search port, funded from what November didn't touch.

## Rules that never bend

- Nothing runs idle; instances self-terminate when their shard ends.
- Every stage's credit cost is reported in the contest thread.
- Antonio launches from his own console (his sign-in, his clicks);
  Muse preps everything so the sitting is short.
