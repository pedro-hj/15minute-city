import networkx as nx
import pytest

from fifteen_minute_city.application.analysis_runner import (
    AccessibilityAnalysisRunner,
)
from fifteen_minute_city.domain.models import Origin, OriginSet


def test_runner_uses_population_as_primary_and_records_node_comparison():
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, travel_time=300.0)
    graph.add_edge(2, 1, travel_time=300.0)
    graph.add_node(3)
    population = OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=(
            Origin("populated", node_id=1, weight=90),
            Origin("isolated", node_id=3, weight=10),
        ),
    )

    outcome = AccessibilityAnalysisRunner().run(
        graph,
        {"health": [2]},
        population_origins=population,
    )

    assert outcome.primary_report.origin_strategy == "population_grid"
    assert outcome.population_report is outcome.primary_report
    assert outcome.node_report.origin_strategy == "network_nodes"
    assert outcome.comparison is not None
    assert outcome.comparison.overall_coverage_delta == pytest.approx(90 - (200 / 3))

    serialized = outcome.to_dict()
    assert "primary_report" not in serialized
    assert serialized["population_report"] is not None
    assert serialized["node_report"] is not None
    assert serialized["comparison"] is not None
