"""Compare row-wise and batched inserts using a disposable PostgreSQL connection."""

from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    Table,
    create_engine,
    insert,
    text,
)


def _measure(operation: Callable[[], None], rounds: int) -> float:
    durations = []
    for _round in range(rounds):
        started_at = time.perf_counter()
        operation()
        durations.append(time.perf_counter() - started_at)
    return statistics.median(durations)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark insert strategies in an isolated temporary table."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--rows", type=int, default=20_000)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument(
        "--confirm-disposable",
        action="store_true",
        help="Required acknowledgement that the target can sustain benchmark load.",
    )
    args = parser.parse_args()
    if not args.confirm_disposable:
        parser.error("--confirm-disposable is required")
    if args.rows <= 0 or args.rounds <= 0:
        parser.error("--rows and --rounds must be greater than zero")

    engine = create_engine(args.database_url)
    if engine.dialect.name != "postgresql":
        parser.error("the persistence benchmark requires PostgreSQL")

    metadata = MetaData()
    benchmark_table = Table(
        "benchmark_node_insert",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("osm_id", Integer, nullable=False),
        Column("x", Float, nullable=False),
        Column("y", Float, nullable=False),
        prefixes=["TEMPORARY"],
    )
    records = [
        {"id": index, "osm_id": 1_000_000 + index, "x": index / 10, "y": 0.0}
        for index in range(args.rows)
    ]

    with engine.connect() as connection:
        benchmark_table.create(connection)

        def clear() -> None:
            connection.execute(text("TRUNCATE benchmark_node_insert"))

        def row_wise() -> None:
            clear()
            for record in records:
                connection.execute(insert(benchmark_table), record)

        def batched() -> None:
            clear()
            for start in range(0, len(records), 5_000):
                connection.execute(
                    insert(benchmark_table), records[start : start + 5_000]
                )

        row_median = _measure(row_wise, args.rounds)
        batch_median = _measure(batched, args.rounds)
        connection.rollback()

    print(f"rows={args.rows} rounds={args.rounds}")
    print(f"row_wise_median_seconds={row_median:.6f}")
    print(f"batched_median_seconds={batch_median:.6f}")
    print(f"speedup={row_median / batch_median:.3f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
