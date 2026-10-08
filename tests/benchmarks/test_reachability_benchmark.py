import networkx as nx
import pytest

from fifteen_minute_city.domain.models import Origin, OriginSet
from fifteen_minute_city.domain.reachability import analyze_accessibility


def _benchmark_case(size: int = 30):
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


@pytest.mark.benchmark
@pytest.mark.parametrize("size", [30, 60, 100], ids=["small", "medium", "large"])
def test_population_weighted_reachability_benchmark(benchmark, size):
    graph, services, origins = _benchmark_case(size)

    report = benchmark(
        analyze_accessibility,
        graph,
        services,
        origins,
        threshold_minutes=15,
    )

    assert report.total_weight == size * size
    assert set(report.categories) == set(services)
