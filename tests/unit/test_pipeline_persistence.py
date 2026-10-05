from contextlib import contextmanager
from types import SimpleNamespace

import networkx as nx

from fifteen_minute_city.application.analysis_runner import AccessibilityAnalysisRunner
from fifteen_minute_city.db.pipelines import algorithm_pipeline as pipeline_module
from fifteen_minute_city.db.pipelines.algorithm_pipeline import AlgorithmPipeline


class FakeSession:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


def test_pipeline_links_node_reachability_to_persisted_service(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, travel_time=300.0)
    graph.add_edge(2, 1, travel_time=300.0)
    outcome = AccessibilityAnalysisRunner().run(
        graph,
        {"health": [2]},
        include_details=True,
    )
    session = FakeSession()
    persisted_reachabilities = []

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(pipeline_module, "session_scope", fake_scope)
    monkeypatch.setattr(
        pipeline_module,
        "list_categories",
        lambda _db: [SimpleNamespace(code="health", id=11)],
    )
    monkeypatch.setattr(
        pipeline_module,
        "get_services_by_execution",
        lambda _db, _execution_id: [
            SimpleNamespace(
                id=200,
                category_id=11,
                representative_node_id=102,
            )
        ],
    )
    monkeypatch.setattr(
        pipeline_module,
        "save_accessibility_report",
        lambda *_args, **_kwargs: ([], SimpleNamespace()),
    )
    monkeypatch.setattr(
        pipeline_module,
        "bulk_save_node_reachabilities",
        lambda _db, data: persisted_reachabilities.extend(data),
    )
    monkeypatch.setattr(
        pipeline_module,
        "update_execution_status",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_module,
        "update_execution_metadata",
        lambda *_args, **_kwargs: None,
    )

    AlgorithmPipeline().save_accessibility_outcome(
        execution_id=7,
        outcome=outcome,
        graph_node_to_db_id={1: 101, 2: 102},
        processing_time_seconds=1.5,
    )

    assert session.committed is True
    assert len(persisted_reachabilities) == 2
    origin_record = next(
        item for item in persisted_reachabilities if item["node_id"] == 101
    )
    assert origin_record["category_id"] == 11
    assert origin_record["closest_service_id"] == 200
    assert origin_record["travel_time_minutes"] == 5.0
    assert origin_record["reachable"] is True
    assert origin_record["within_threshold"] is True
