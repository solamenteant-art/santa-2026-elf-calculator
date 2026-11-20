# Shard jobs

Push a JSON file here to start a grind shard. Format:

```json
{"start": 0, "end": 100, "k": 10, "seed_base": 300000, "min_len": 400}
```

- `start` / `end`: puzzle index range (end exclusive)
- `k`: randomized target orders tried per puzzle
- `seed_base`: must be unique per shard (results file is named by it)
- `min_len`: only puzzles whose incumbent program is at least this long
  are re-solved

Results are committed to the `shards` branch under `results/`.
