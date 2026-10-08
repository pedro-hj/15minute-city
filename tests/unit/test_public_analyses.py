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
    west = _tile(input_dir, "grade_id04", box(-46.01, -24.01, -45.99, -23.99), 80, "west")
    east = _tile(input_dir, "grade_id13", box(-45.91, -24.01, -45.89, -23.99), 20, "east")
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
        [a, b], _graph(), population_column="TOTAL",
        id_column="ID_UNICO", boundary=boundary,
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

    assert AnalysisSubmission(ibge_code="3541000").ibge_code == "3541000"
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnalysisSubmission(ibge_code="999")


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
