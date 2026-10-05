# Performance benchmarks

## Real end-to-end execution

The real-data benchmark uses Praia Grande and these files by default:

- `data/input/brazil-260922.osm.pbf`;
- `data/input/grade_id25.zip`.

Run it with:

```bash
uv run python scripts/benchmark_real_execution.py \
  --boundary data/cache/2843d9cc161b09ba937be5b0/boundary.geojson
```

The JSON report is saved under `data/output/benchmarks/<city-state>/`. It
records duration, CPU use and RAM use for the graph, services, population grid,
accessibility calculation and serialization stages. It also records the total,
input files, cache status and relevant hardware information.

For a cold-cache measurement, provide a new cache directory:

```bash
uv run python scripts/benchmark_real_execution.py \
  --boundary data/cache/2843d9cc161b09ba937be5b0/boundary.geojson \
  --cache-dir /tmp/benchmark-new-cache
```

Warm- and cold-cache results represent different scenarios and must be reported
separately.

### Praia Grande reference results

Measurements made on 2026-10-05 with an Intel Core i7-13620H, 10 physical
cores, 16 logical processors and approximately 23.2 GiB of RAM:

| Scenario | Total time | Peak RAM | Average total CPU |
| --- | ---: | ---: | ---: |
| Cold cache | 13.08 s | 2,524 MiB | 44.75% |
| Warm cache | 3.03 s | 631 MiB | 6.26% |

Cold-cache stage durations:

| Stage | Duration |
| --- | ---: |
| Graph extraction and construction | 11.71 s |
| Service extraction | 0.41 s |
| Population grid | 0.81 s |
| Accessibility calculation | 0.14 s |
| Result serialization | < 0.01 s |

## Synthetic accessibility benchmark

The deterministic benchmark measures only the accessibility calculation:

```bash
uv run pytest -q tests/benchmarks/test_reachability_benchmark.py \
  --benchmark-min-rounds=5
```

Reference results:

| Grid | Nodes | Edges | Mean |
| --- | ---: | ---: | ---: |
| 30 x 30 | 900 | 3,480 | about 7 ms |
| 60 x 60 | 3,600 | 14,160 | about 29 ms |
| 100 x 100 | 10,000 | 39,600 | about 93 ms |

Python allocation profiling can be reproduced with:

```bash
uv run python scripts/profile_reachability.py
```

## Database persistence benchmark

The persistence benchmark must use a disposable PostgreSQL/PostGIS database:

```bash
uv run python scripts/benchmark_persistence.py \
  --database-url postgresql+psycopg://user:password@localhost/benchmark \
  --rows 20000 \
  --rounds 5 \
  --confirm-disposable
```

It compares individual inserts with batches of 5,000 rows and rolls back the
transaction at the end.
