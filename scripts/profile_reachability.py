"""Report runtime and peak Python allocation for deterministic graph sizes."""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc

import networkx as nx

from fifteen_minute_city.domain.models import Origin, OriginSet
from fifteen_minute_city.domain.reachability import analyze_accessibility


def build_case(size: int):
    base = nx.grid_2d_graph(size, size)
    graph = nx.MultiDiGraph()
    node_map = {node: index for index, node in enumerate(base.nodes)}
    for source, target in base.edges:
        u = node_map[source]
        v = node_map[target]
        graph.add_edge(u, v, travel_time=60.0)
        graph.add_edge(v, u, travel_time=60.0)
    origins = OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=tuple(
            Origin(f"cell:{node}", node_id=node, weight=1.0) for node in graph.nodes
        ),
    )
    last = size * size - 1
    services = {
        "health": [0],
        "education": [size - 1],
        "food": [last - size + 1],
        "culture": [last],
    }
    return graph, services, origins


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[30, 60, 100])
    args = parser.parse_args()
    measurements = []
    for size in args.sizes:
        if size <= 1:
            parser.error("every size must be greater than one")
        graph, services, origins = build_case(size)
        tracemalloc.start()
        started_at = time.perf_counter()
        analyze_accessibility(graph, services, origins)
        elapsed = time.perf_counter() - started_at
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        measurements.append(
            {
                "grid": f"{size}x{size}",
                "nodes": size * size,
                "edges": graph.number_of_edges(),
                "seconds": round(elapsed, 6),
                "peak_python_mib": round(peak / 1024 / 1024, 3),
            }
        )
    print(json.dumps(measurements, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
