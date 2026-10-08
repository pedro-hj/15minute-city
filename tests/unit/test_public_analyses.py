"""Public analysis admission and municipality population tile discovery."""

from __future__ import annotations

import json
from zipfile import ZipFile

import geopandas as gpd
import networkx as nx
import pytest
from fastapi import HTTPException
from shapely.geometry import box

from fifteen_minute_city.api import analysis_service
from fifteen_minute_city.api.analysis_routes import AnalysisSubmission
from fifteen_minute_city.infrastructure import ibge
from fifteen_minute_city.infrastructure.origins import load_population_grid
from fifteen_minute_city.infrastructure.population_catalog import (
    grid_catalog,
    select_population_grids,
)


def _tile(root, name, geometry, population, id_):
    folder = root / f"{name}_files"
    folder.mkdir()
    shp = folder / f"{name}.shp"
    gpd.GeoDataFrame(
        {"ID_UNICO": [id_], "TOTAL": [population], "geometry": [geometry]},
        crs="EPSG:4326",
    ).to_file(shp)
    dest = root / f"{name}.zip"
    with ZipFile(dest, "w") as archive:
        for member in folder.iterdir():
            archive.write(member, arcname=member.name)
    return dest


def _graph():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=-46.0, y=-24.0)
    graph.add_node(2, x=-45.9, y=-24.0)
    graph.add_edge(1, 2, travel_time=120)
    graph.add_edge(2, 1, travel_time=120)
    return graph


def test_tile_catalog_discovers_overlapping_tiles_from_geography(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    west = _tile(
        input_dir, "grade_id04", box(-46.01, -24.01, -45.99, -23.99), 80, "west"
    )
    east = _tile(
        input_dir, "grade_id13", box(-45.91, -24.01, -45.89, -23.99), 20, "east"
    )
    _tile(input_dir, "grade_id14", box(-40.01, -20.01, -39.99, -19.99), 10, "far")

    boundary = gpd.GeoDataFrame(
        {"geometry": [box(-46.02, -24.02, -45.88, -23.98)]},
        crs="EPSG:4326",
    )
    selected = select_population_grids(
        boundary, input_dir=input_dir, cache_dir=tmp_path / "cache"
    )
    assert selected == [west, east]
    catalog = grid_catalog(input_dir, tmp_path / "cache")
    assert len(catalog) == 3
    cached = json.loads(
        (tmp_path / "cache" / "population-grids.json").read_text(encoding="utf-8")
    )
    assert cached["version"] == 1

    origins = load_population_grid(
        selected,
        _graph(),
        population_column="TOTAL",
        id_column="ID_UNICO",
        boundary=boundary,
    )
    assert origins.total_weight == 100
    assert len(origins.origins) == 2
    assert origins.metadata["selected_tile_count"] == 2


def test_deduplicates_cell_ids_from_overlapping_archives(tmp_path):
    a = _tile(tmp_path, "grade_id23", box(-46.01, -24.01, -45.99, -23.99), 80, "same")
    b = _tile(tmp_path, "grade_id24", box(-46.01, -24.01, -45.99, -23.99), 80, "same")
    boundary = gpd.GeoDataFrame(
        {"geometry": [box(-46.02, -24.02, -45.98, -23.98)]},
        crs="EPSG:4326",
    )
    origins = load_population_grid(
        [a, b],
        _graph(),
        population_column="TOTAL",
        id_column="ID_UNICO",
        boundary=boundary,
    )
    assert origins.total_weight == 80
    assert len(origins.origins) == 1


def test_public_code_validation_and_protected_ip_hash(monkeypatch):
    monkeypatch.setenv("ANALYSES_IP_HMAC_SECRET", "x" * 40)
    token = analysis_service._requester_hash("192.0.2.9")
    assert token != "192.0.2.9"
    assert token == analysis_service._requester_hash("192.0.2.9")
    assert token != analysis_service._requester_hash("192.0.2.10")
    with pytest.raises(HTTPException) as exc:
        analysis_service._requester_hash("spoofed")
    assert exc.value.status_code == 503

    payload = AnalysisSubmission(
        city=" Praia Grande ", state="São Paulo", country="Brazil"
    )
    assert payload.city == "Praia Grande"
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnalysisSubmission(city="  ", state="São Paulo", country="Brazil")
    with pytest.raises(ValidationError):
        AnalysisSubmission(ibge_code="3541000")


def test_ibge_code_resolution_is_strict_and_non_dynamic(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def read(self, n):
            return json.dumps(
                {
                    "id": 3541000,
                    "nome": "Praia Grande",
                    "microrregiao": {"mesorregiao": {"UF": {"nome": "São Paulo"}}},
                }
            ).encode()

    monkeypatch.setattr(ibge, "urlopen", lambda *args, **kwargs: FakeResponse())
    ibge.municipality_by_code.cache_clear()
    assert ibge.municipality_by_code("3541000") == ("Praia Grande", "São Paulo")
    with pytest.raises(ValueError):
        ibge.municipality_by_code("../passwd")


def test_rate_limit_parameter_requires_sensible_minimum(monkeypatch):
    monkeypatch.setenv("ANALYSES_RATE_LIMIT_SECONDS", "20")
    with pytest.raises(HTTPException) as exc:
        analysis_service._seconds("ANALYSES_RATE_LIMIT_SECONDS", 3600, 60)
    assert exc.value.status_code == 503


def test_public_submission_has_no_api_key_requirement():
    from fifteen_minute_city.api.app import app

    operation = app.openapi()["paths"]["/api/v1/analyses"]["post"]
    assert "security" not in operation
    assert "/api/v1/analyses/{request_id}" in app.openapi()["paths"]


def test_named_municipalities_resolve_to_official_codes(monkeypatch):
    from fifteen_minute_city.infrastructure.ibge import municipality_by_location

    lookup = {
        "SP": (("Praia Grande", "3541000"), ("São Vicente", "3551009")),
        "SC": (("Praia Grande", "4213807"),),
    }
    monkeypatch.setattr(
        ibge, "_municipalities_for_state", lambda uf: lookup[uf]
    )
    assert municipality_by_location("praia grande", "Sao Paulo", "BR") == (
        "3541000", "Praia Grande", "São Paulo"
    )
    assert municipality_by_location("PRAIA GRANDE", "SC", "Brasil") == (
        "4213807", "Praia Grande", "Santa Catarina"
    )
    with pytest.raises(ValueError, match="not found"):
        municipality_by_location("inexistente", "São Paulo", "Brazil")
    with pytest.raises(ValueError, match="Only cities in Brazil"):
        municipality_by_location("Praia Grande", "SP", "Portugal")
    with pytest.raises(ValueError, match="state not recognized"):
        municipality_by_location("Praia Grande", "ZZ", "Brasil")


def test_official_state_municipality_listing_is_cached(monkeypatch):
    seen = []

    def fake_fetch(url, max_bytes):
        seen.append((url, max_bytes))
        return [{"id": 3541000, "nome": "Praia Grande"}]

    monkeypatch.setattr(ibge, "_fetch_json", fake_fetch)
    ibge._municipalities_for_state.cache_clear()
    expected = (("Praia Grande", "3541000"),)
    assert ibge._municipalities_for_state("SP") == expected
    assert ibge._municipalities_for_state("SP") == expected
    assert len(seen) == 1
    assert seen[0][0].endswith("/estados/SP/municipios")


def test_post_accepts_location_without_ibge_code_or_api_key(monkeypatch):
    from fastapi.testclient import TestClient
    from fifteen_minute_city.api.app import app
    from fifteen_minute_city.api import analysis_routes

    seen = []

    def fake_resolve(city, state, country):
        seen.append(("resolve", city, state, country))
        return "3541000", "Praia Grande", "São Paulo"

    def fake_submit(code, city, state, ip):
        seen.append(("submit", code, city, state, ip))
        return {
            "request_id": "test-uuid",
            "ibge_code": code,
            "city": city,
            "state": state,
            "status": "queued",
            "requested_at": None,
            "city_id": None,
            "results_url": None,
        }, 202

    monkeypatch.setattr(analysis_routes, "municipality_by_location", fake_resolve)
    monkeypatch.setattr(analysis_routes, "submit", fake_submit)
    response = TestClient(app).post(
        "/api/v1/analyses",
        json={"city": "Praia Grande", "state": "São Paulo", "country": "Brazil"},
    )
    assert response.status_code == 202
    assert response.json()["ibge_code"] == "3541000"
    assert seen[0] == ("resolve", "Praia Grande", "São Paulo", "Brazil")
    assert seen[1][0:4] == ("submit", "3541000", "Praia Grande", "São Paulo")

    invalid = TestClient(app).post(
        "/api/v1/analyses", json={"ibge_code": "3541000"}
    )
    assert invalid.status_code == 422
