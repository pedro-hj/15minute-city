import networkx as nx
import pytest

from fifteen_minute_city.domain.models import Origin, OriginSet
from fifteen_minute_city.domain.reachability import (
    _weighted_median,
    analyze_accessibility,
    compare_accessibility,
)


def _walking_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, travel_time=300.0)
    graph.add_edge(2, 1, travel_time=300.0)
    graph.add_edge(2, 3, travel_time=900.0)
    graph.add_edge(3, 2, travel_time=900.0)
    graph.add_node(4)
    return graph


def test_weighted_median_uses_population_weight() -> None:
    assert _weighted_median([(5, 10), (20, 90)]) == 20
    assert _weighted_median([]) is None


def test_weighted_coverage_and_unreachable_population() -> None:
    origins = OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=(
            Origin("a", node_id=1, weight=60),
            Origin("b", node_id=2, weight=30),
            Origin("c", node_id=4, weight=10),
        ),
    )

    report = analyze_accessibility(
        _walking_graph(),
        {
            "health": [2],
            "education": [3],
        },
        origins,
        threshold_minutes=15,
        include_details=True,
    )

    assert report.categories["health"].coverage_percentage == 90.0
    assert report.categories["health"].unreachable_percentage == 10.0
    assert report.categories["education"].coverage_percentage == 30.0
    assert report.categories["education"].unreachable_percentage == 10.0
    assert report.overall_coverage_percentage == 30.0
    assert report.overall_coverage_percentage == 30.0
    assert report.overall_unreachable_percentage == 10.0


def test_empty_category_marks_every_origin_unreachable() -> None:
    origins = OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=(Origin("a", node_id=1, weight=100),),
    )

    report = analyze_accessibility(
        _walking_graph(),
        {"culture": []},
        origins,
    )

    metrics = report.categories["culture"]
    assert metrics.coverage_percentage == 0.0
    assert metrics.unreachable_percentage == 100.0
    assert metrics.mean_travel_time_minutes is None
    assert report.overall_coverage_percentage == 0.0


def test_directed_graph_calculates_route_from_origin_to_service() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, travel_time=300.0)
    origins = OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=(Origin("a", node_id=1, weight=1),),
    )

    report = analyze_accessibility(
        graph,
        {"health": [2]},
        origins,
        include_details=True,
    )

    detail = report.categories["health"].details[0]
    assert detail.reachable is True
    assert detail.travel_time_minutes == 5.0
    assert detail.nearest_service_node_id == 2


def test_population_and_node_reports_are_compared_by_percentage_points() -> None:
    graph = _walking_graph()
    population_origins = OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=(
            Origin("populated", node_id=1, weight=90),
            Origin("isolated", node_id=4, weight=10),
        ),
    )
    node_origins = OriginSet(
        strategy="network_nodes",
        weight_unit="node_count",
        origins=tuple(
            Origin(f"node:{node}", node_id=node, weight=1) for node in graph.nodes
        ),
    )

    population_report = analyze_accessibility(
        graph, {"health": [2]}, population_origins
    )
    node_report = analyze_accessibility(graph, {"health": [2]}, node_origins)
    comparison = compare_accessibility(population_report, node_report)

    assert population_report.overall_coverage_percentage == 90.0
    assert node_report.overall_coverage_percentage == 75.0
    assert comparison.overall_coverage_delta == 15.0
    assert comparison.category_unreachable_delta["health"] == -15.0


@pytest.mark.parametrize("threshold", [0, -1, float("inf")])
def test_invalid_threshold_is_rejected(threshold: float) -> None:
    origins = OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=(Origin("a", node_id=1, weight=1),),
    )

    with pytest.raises(ValueError, match="threshold_minutes"):
        analyze_accessibility(
            _walking_graph(),
            {"health": [2]},
            origins,
            threshold_minutes=threshold,
        )
