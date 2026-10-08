import datetime
from types import SimpleNamespace

import pytest

from fifteen_minute_city.api import service as service_module
from fifteen_minute_city.api.service import (
    build_comparison,
    build_metric_response,
    build_strategy_report,
    extract_metric,
    resolve_strategy,
)


class _Rows:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[object, object]]:
        return self.rows


class _ReportSession:
    def __init__(self, summary: object, rows: list[tuple[object, object]]) -> None:
        self.summary = summary
        self.rows = rows

    def get(self, model, identity):
        return self.summary

    def execute(self, statement):
        return _Rows(self.rows)


def _report(
    strategy: str,
    *,
    category_coverage: float,
    overall_coverage: float,
) -> dict:
    return {
        "origin_strategy": strategy,
        "weight_unit": "nodes" if strategy == "network_nodes" else "population",
        "threshold_minutes": 15.0,
        "total_weight": 100.0,
        "categories": {
            "health": {
                "category": "health",
                "total_weight": 100.0,
                "reachable_weight": 90.0,
                "within_threshold_weight": category_coverage,
                "unreachable_weight": 10.0,
                "coverage_percentage": category_coverage,
                "unreachable_percentage": 10.0,
                "mean_travel_time_minutes": 8.5,
                "median_travel_time_minutes": 8.0,
            }
        },
        "overall_coverage_percentage": overall_coverage,
        "overall_unreachable_percentage": 10.0,
        "metadata": {},
    }


def test_public_strategies_map_to_persisted_names() -> None:
    assert resolve_strategy("nodes") == "network_nodes"
    assert resolve_strategy("population") == "population_grid"
    assert resolve_strategy("unknown") is None


def test_comparison_matches_detailed_json_semantics() -> None:
    population = _report(
        "population_grid",
        category_coverage=80.0,
        overall_coverage=70.0,
    )
    nodes = _report(
        "network_nodes",
        category_coverage=65.0,
        overall_coverage=55.0,
    )

    comparison = build_comparison(population, nodes)

    assert comparison["calculation"] == "population_report - node_report"
    assert comparison["category_coverage_delta"] == {"health": 15.0}
    assert comparison["overall_coverage_delta"] == 15.0


def test_builds_detailed_strategy_report_from_aggregated_rows() -> None:
    summary = SimpleNamespace(
        weight_unit="population",
        threshold_minutes=15.0,
        total_weight=1_000.0,
        overall_coverage_percentage=72.5,
        overall_unreachable_percentage=4.0,
    )
    index = SimpleNamespace(
        total_weight=1_000.0,
        reachable_weight=960.0,
        within_threshold_weight=800.0,
        unreachable_weight=40.0,
        percentage_within_threshold=80.0,
        unreachable_percentage=4.0,
        mean_travel_time_minutes=8.5,
        median_travel_time_minutes=8.0,
    )
    category = SimpleNamespace(code="health")
    session = _ReportSession(summary, [(index, category)])

    report = build_strategy_report(session, 7, "population_grid")

    assert report["origin_strategy"] == "population_grid"
    assert report["categories"]["health"]["coverage_percentage"] == 80.0
    assert report["overall_coverage_percentage"] == 72.5


def test_extracts_category_and_overall_metrics() -> None:
    report = _report(
        "network_nodes",
        category_coverage=65.0,
        overall_coverage=55.0,
    )

    assert extract_metric(report, "coverage_percentage", category="health") == 65.0
    assert extract_metric(report, "overall_coverage_percentage") == 55.0


def test_rejects_unknown_metric_or_category() -> None:
    report = _report(
        "network_nodes",
        category_coverage=65.0,
        overall_coverage=55.0,
    )

    with pytest.raises(KeyError):
        extract_metric(report, "score", category="health")
    with pytest.raises(LookupError):
        extract_metric(report, "coverage_percentage", category="unknown")


def test_metric_response_includes_execution_context() -> None:
    processed_at = datetime.datetime(2026, 10, 6, tzinfo=datetime.UTC)
    execution = SimpleNamespace(id=7, city_id=3, processed_at=processed_at)
    report = _report(
        "network_nodes",
        category_coverage=65.0,
        overall_coverage=55.0,
    )

    response = build_metric_response(
        execution,
        "nodes",
        report,
        "coverage_percentage",
        category="health",
    )

    assert response == {
        "city_id": 3,
        "execution_id": 7,
        "processed_at": processed_at,
        "strategy": "nodes",
        "category": "health",
        "metric": "coverage_percentage",
        "value": 65.0,
        "unit": "percent",
        "threshold_minutes": 15.0,
    }


def test_detailed_result_uses_persisted_strategy_names(monkeypatch) -> None:
    processed_at = datetime.datetime(2026, 10, 6, tzinfo=datetime.UTC)
    execution = SimpleNamespace(
        id=7,
        city_id=3,
        processed_at=processed_at,
        status="completed",
        speed_kmh=3.0,
        threshold_minutes=15.0,
        network_type="walk",
        execution_time_seconds=1.5,
    )
    strategies = []

    def fake_report(_db, _execution_id, strategy):
        strategies.append(strategy)
        return None

    monkeypatch.setattr(service_module, "build_strategy_report", fake_report)

    result = service_module.build_detailed_result(object(), execution)

    assert strategies == ["network_nodes", "population_grid"]
    assert result["node_report"] is None
    assert result["population_report"] is None
    assert result["comparison"] is None
