import networkx as nx

from fifteen_minute_city.db.models.metrics import AccessibilitySummary, CityIndex
from fifteen_minute_city.db.services.metrics_service import save_accessibility_report
from fifteen_minute_city.domain.models import Origin, OriginSet
from fifteen_minute_city.domain.reachability import analyze_accessibility


class FakeSession:
    def __init__(self):
        self.merged = []
        self.flushed = False

    def merge(self, instance):
        self.merged.append(instance)
        return instance

    def flush(self):
        self.flushed = True


def test_domain_report_maps_to_explicit_database_metrics():
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, travel_time=300.0)
    graph.add_edge(2, 1, travel_time=300.0)
    report = analyze_accessibility(
        graph,
        {"health": [2]},
        OriginSet(
            strategy="population_grid",
            weight_unit="population",
            origins=(Origin("cell", node_id=1, weight=50),),
        ),
    )
    session = FakeSession()

    indices, summary = save_accessibility_report(
        session,
        execution_id=7,
        report=report,
        category_id_map={"health": 11},
    )

    assert session.flushed is True
    assert len(indices) == 1
    assert isinstance(indices[0], CityIndex)
    assert indices[0].origin_strategy == "population_grid"
    assert indices[0].percentage_within_threshold == 100.0
    assert indices[0].unreachable_percentage == 0.0
    assert isinstance(summary, AccessibilitySummary)
    assert summary.overall_score == 100.0
