"""HTTP contract for service location optimization."""

import asyncio
import json

import networkx as nx
import numpy as np
import pytest

from fifteen_minute_city.api import routes
from fifteen_minute_city.api.app import app
from fifteen_minute_city.application.server_simulation import (
    InvalidSimulationPackage,
    decode_package,
)
from fifteen_minute_city.application.simulation_package import build_package
from fifteen_minute_city.db.connection import get_db


def _sample_bundle():
    graph = nx.MultiDiGraph()
    for node in range(3):
        graph.add_node(node, x=node * 0.001, y=0.0)
    for origin, target in ((0, 1), (1, 0), (1, 2), (2, 1)):
        graph.add_edge(origin, target, length=250)
    return decode_package(
        build_package(
            graph,
            execution_id=7,
            speed_kmh=3.0,
            threshold_minutes=5.0,
            categories=["health"],
            population_by_osm={0: 10.0, 1: 0.0, 2: 10.0},
            baseline_minutes={(node, "health"): None for node in range(3)},
            pbf_checksum="test",
            graph_cache_key="test",
        )
    )


async def _post_optimization(
    body: dict, *, authenticated: bool = True
) -> tuple[int, dict]:
    body_bytes = json.dumps(body).encode()
    headers = [(b"content-type", b"application/json")]
    if authenticated:
        headers.append((b"x-api-key", b"test-key"))
    messages = []
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/executions/7/optimize",
            "raw_path": b"/api/v1/executions/7/optimize",
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "server": ("testserver", 80),
            "client": ("testclient", 12345),
        },
        receive,
        send,
    )
    status = next(
        message["status"]
        for message in messages
        if message["type"] == "http.response.start"
    )
    response_bytes = b"".join(
        message["body"]
        for message in messages
        if message["type"] == "http.response.body"
    )
    return status, json.loads(response_bytes)


@pytest.fixture
def configured_api(monkeypatch):
    bundle = _sample_bundle()
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.delenv("OPTIMIZATION_MAX_NODES", raising=False)
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: object())
    monkeypatch.setattr(
        routes.service, "get_completed_execution", lambda _db, _id: object()
    )
    monkeypatch.setattr(routes, "load_execution_package", lambda _folder, _id: bundle)
    return bundle


def test_optimization_http_returns_greedy_recommendation(configured_api):
    baseline_before = configured_api.baseline.copy()

    status, result = asyncio.run(_post_optimization({"category": "health", "k": 2}))

    assert status == 200
    assert result["execution_id"] == 7
    assert result["algorithm"] == "greedy"
    assert result["k_requested"] == 2
    assert result["threshold_minutes"] == 5.0
    assert result["baseline_coverage_percentage"] == 0.0
    assert result["simulated_coverage_percentage"] == 100.0
    assert result["coverage_delta_percentage_points"] == 100.0
    assert len(result["locations"]) == 1
    assert result["locations"][0]["node_id"] == 1
    assert result["locations"][0]["marginal_population"] == 20.0
    np.testing.assert_array_equal(configured_api.baseline, baseline_before)


def test_optimization_http_applies_threshold_and_minimum_distance(configured_api):
    unrestricted_status, unrestricted = asyncio.run(
        _post_optimization({"category": "health", "k": 2, "threshold_minutes": 1})
    )
    restricted_status, restricted = asyncio.run(
        _post_optimization(
            {
                "category": "health",
                "k": 2,
                "threshold_minutes": 1,
                "min_distance_m": 300,
            }
        )
    )

    assert unrestricted_status == restricted_status == 200
    assert unrestricted["simulated_coverage_percentage"] == 100.0
    assert restricted["simulated_coverage_percentage"] == 50.0
    assert restricted["threshold_minutes"] == 1.0
    assert restricted["min_distance_m"] == 300.0
    assert len(restricted["locations"]) == 1


def test_optimization_http_requires_api_key(configured_api):
    status, _result = asyncio.run(
        _post_optimization({"category": "health"}, authenticated=False)
    )
    assert status == 401


def test_optimization_http_continues_with_manual_and_previous_services(configured_api):
    body = {
        "category": "health",
        "k": 1,
        "threshold_minutes": 1,
        "existing_services": [
            {
                "category": "health",
                "latitude": 0,
                "longitude": 0,
                "name": "Manual service",
            }
        ],
    }
    status, result = asyncio.run(_post_optimization(body))
    assert status == 200
    assert result["baseline_coverage_percentage"] == 0
    assert result["initial_coverage_percentage"] == 50
    assert result["simulated_coverage_percentage"] == 100
    assert result["coverage_delta_percentage_points"] == 100
    assert result["incremental_coverage_delta_percentage_points"] == 50
    point = result["locations"][0]
    assert point["node_id"] == 2
    body["existing_services"].append(
        {
            "category": "health",
            "latitude": point["latitude"],
            "longitude": point["longitude"],
        }
    )
    status, continued = asyncio.run(_post_optimization(body))
    assert status == 200
    assert continued["locations"] == []
    assert continued["initial_coverage_percentage"] == 100
    assert continued["incremental_coverage_delta_percentage_points"] == 0


@pytest.mark.parametrize(
    "services",
    [
        [{"category": "health", "latitude": 91, "longitude": 0}],
        [{"category": "health", "latitude": 80, "longitude": 80}],
        [{"category": "culture", "latitude": 0, "longitude": 0}],
        [{"category": "health", "latitude": 0}],
        [{"category": "health", "latitude": 0, "longitude": 0}] * 201,
    ],
)
def test_optimization_http_validates_existing_services(configured_api, services):
    status, _result = asyncio.run(
        _post_optimization(
            {
                "category": "health",
                "existing_services": services,
            }
        )
    )
    assert status == 422


@pytest.mark.parametrize(
    "body",
    [
        {"category": "health", "k": 0},
        {"category": "health", "k": 4},
        {"category": "health", "algorithm": "unknown"},
        {"category": "health", "threshold_minutes": "NaN"},
        {"category": "health", "min_distance_m": -1},
        {"category": "culture"},
    ],
)
def test_optimization_http_rejects_invalid_requests(configured_api, body):
    status, _result = asyncio.run(_post_optimization(body))
    assert status == 422


def test_optimization_http_requires_completed_execution(configured_api, monkeypatch):
    monkeypatch.setattr(
        routes.service, "get_completed_execution", lambda _db, _id: None
    )
    status, _result = asyncio.run(_post_optimization({"category": "health"}))
    assert status == 404


def test_optimization_http_requires_package(configured_api, monkeypatch):
    def missing_package(_folder, _execution_id):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(routes, "load_execution_package", missing_package)
    status, _result = asyncio.run(_post_optimization({"category": "health"}))
    assert status == 404


def test_optimization_http_rejects_invalid_package(configured_api, monkeypatch):
    def invalid_package(_folder, _execution_id):
        raise InvalidSimulationPackage("corrupt")

    monkeypatch.setattr(routes, "load_execution_package", invalid_package)
    status, _result = asyncio.run(_post_optimization({"category": "health"}))
    assert status == 503


def test_optimization_http_enforces_node_limit(configured_api, monkeypatch):
    monkeypatch.setenv("OPTIMIZATION_MAX_NODES", "2")
    status, result = asyncio.run(_post_optimization({"category": "health"}))
    assert status == 503
    assert "2 nodes" in result["detail"]
