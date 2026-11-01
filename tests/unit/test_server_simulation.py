"""Tests of the VPS-side simulation engine and the API contract."""

from pathlib import Path

import networkx as nx
import numpy as np
import pytest
from fastapi import HTTPException

from fifteen_minute_city.api import routes
from fifteen_minute_city.api.schemas import SimulationRequest, SimulationResponse
from fifteen_minute_city.application.server_simulation import (
    InvalidSimulationPackage,
    InvalidSimulationRequest,
    decode_package,
    simulate,
)
from fifteen_minute_city.application.simulation_package import build_package


def sample_bundle():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    for node, longitude in [(11, 0), (22, 0.005), (33, 0.01)]:
        graph.add_node(node, x=longitude, y=0.0)
    graph.add_edge(11, 22, length=1000)
    graph.add_edge(22, 33, length=1000)
    raw = build_package(
        graph,
        execution_id=7,
        speed_kmh=3,
        threshold_minutes=15,
        categories=["health", "food"],
        population_by_osm={11: 50, 22: 0, 33: 50},
        baseline_minutes={
            (11, "health"): 0,
            (11, "food"): 40,
            (22, "health"): 20,
            (22, "food"): 20,
            (33, "health"): 40,
            (33, "food"): 0,
        },
        pbf_checksum="a" * 64,
        graph_cache_key="b" * 24,
    )
    return decode_package(raw)


def test_response_includes_only_affected_category_for_both_strategies():
    bundle = sample_bundle()
    baseline_before = bundle.baseline.copy()
    result = simulate(
        bundle,
        [{"category": "health", "name": "UBS", "latitude": 0, "longitude": 0.01}],
    )
    assert result["execution_id"] == 7
    assert list(result["results"]) == ["health"]
    assert "baseline" not in result
    assert "simulated" not in result
    assert "delta" not in result

    health = result["results"]["health"]
    assert set(health) == {"population", "nodes"}
    population = health["population"]
    assert population["before"]["coverage_percentage"] == 50
    assert population["after"]["coverage_percentage"] == 100
    assert population["coverage_delta_percentage_points"] == 50
    assert population["after"]["mean_travel_time_minutes"] == 0
    assert health["nodes"]["before"]["coverage_percentage"] == pytest.approx(100 / 3)
    assert health["nodes"]["after"]["coverage_percentage"] == pytest.approx(200 / 3)
    assert result["added_services"][0]["snap_distance_m"] == 0
    assert result["processing_time_ms"] >= 0
    np.testing.assert_array_equal(bundle.baseline, baseline_before)


def test_multiple_services_report_each_changed_category_only():
    bundle = sample_bundle()
    result = simulate(
        bundle,
        [
            {"category": "health", "latitude": 0, "longitude": 0.01},
            {"category": "health", "latitude": 0, "longitude": 0.01},
            {"category": "food", "latitude": 0, "longitude": 0},
        ],
    )
    assert set(result["results"]) == {"health", "food"}
    for category in ("health", "food"):
        assert (
            result["results"][category]["population"]["after"]["coverage_percentage"]
            == 100
        )
        assert set(result["results"][category]) == {"population", "nodes"}
    # No superfluous overall metrics are returned.
    assert all(
        "overall_coverage_percentage" not in str(value)
        for value in result["results"].values()
    )


def test_reject_unknown_categories_and_far_away_points():
    bundle = sample_bundle()
    with pytest.raises(InvalidSimulationRequest, match="not analyzed"):
        simulate(bundle, [{"category": "culture", "longitude": 0, "latitude": 0}])
    with pytest.raises(InvalidSimulationRequest, match="too far"):
        simulate(bundle, [{"category": "health", "longitude": 1, "latitude": 1}])


def test_corrupted_binary_is_rejected():
    with pytest.raises(InvalidSimulationPackage, match="header"):
        decode_package(b"FMC1")


def test_api_routes_server_side_and_removes_package_download(monkeypatch):
    routes_list = [
        route
        for route in routes.router.routes
        if getattr(route, "path", "").startswith("/api/v1/executions/")
    ]
    assert any(
        route.path == "/api/v1/executions/{execution_id}/simulate"
        and "POST" in route.methods
        for route in routes_list
    )
    assert not any("simulation-package" in route.path for route in routes_list)

    monkeypatch.setattr(
        routes.service, "get_completed_execution", lambda _db, _id: object()
    )
    monkeypatch.setattr(
        routes, "load_execution_package", lambda _folder, _id: sample_bundle()
    )
    scenario = SimulationRequest.model_validate(
        {"services": [{"category": "health", "latitude": 0, "longitude": 0.01}]}
    )
    result = routes.simulate_execution(7, scenario, object())
    assert (
        result["results"]["health"]["population"]["after"]["coverage_percentage"] == 100
    )
    SimulationResponse.model_validate(result)

    invalid = SimulationRequest.model_validate(
        {"services": [{"category": "culture", "latitude": 0, "longitude": 0.01}]}
    )
    with pytest.raises(HTTPException) as error:
        routes.simulate_execution(7, invalid, object())
    assert error.value.status_code == 422


def test_api_requires_prepared_package(monkeypatch):
    monkeypatch.setattr(
        routes.service, "get_completed_execution", lambda _db, _id: object()
    )

    def missing_bundle(_folder: Path, _execution_id: int):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(routes, "load_execution_package", missing_bundle)
    scenario = SimulationRequest.model_validate(
        {"services": [{"category": "health", "latitude": 0, "longitude": 0}]}
    )
    with pytest.raises(HTTPException) as error:
        routes.simulate_execution(7, scenario, object())
    assert error.value.status_code == 404


def test_simulation_reports_overall_before_and_after():
    result = simulate(
        sample_bundle(),
        [
            {"category": "health", "latitude": 0, "longitude": 0.01},
            {"category": "food", "latitude": 0, "longitude": 0},
        ],
    )

    population = result["overall"]["population"]
    assert population["before"]["coverage_percentage"] == 0
    assert population["after"]["coverage_percentage"] == 100
    assert population["coverage_delta_percentage_points"] == 100
    nodes = result["overall"]["nodes"]
    assert nodes["after"]["coverage_percentage"] == pytest.approx(200 / 3)
