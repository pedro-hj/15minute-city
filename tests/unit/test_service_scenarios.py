"""Regression tests for hypothetical essential-service simulations."""

from __future__ import annotations

import json

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import Point, box

from fifteen_minute_city.application.scenario_services import load_service_scenario
from fifteen_minute_city.core.modules.locales import Region
from fifteen_minute_city.domain.models import Origin, OriginSet
from fifteen_minute_city.infrastructure.osm.services import snap_services_to_graph
from fifteen_minute_city.main import build_parser, format_simulation_output, main


def _scenario(tmp_path, features):
    path = tmp_path / "scenario.geojson"
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )
    return path


def _feature(category="health", coords=(0.009, 0.0), name="New clinic"):
    return {
        "type": "Feature",
        "properties": {"name": name, "category": category},
        "geometry": {"type": "Point", "coordinates": list(coords)},
    }


def _boundary():
    return gpd.GeoDataFrame(
        {"geometry": [box(-0.01, -0.01, 0.01, 0.01)]},
        crs="EPSG:4326",
    )


def test_scenario_accepts_multiple_locations_and_valid_categories(tmp_path):
    path = _scenario(
        tmp_path,
        [_feature(), _feature(category="food", coords=(0.001, 0.0), name="Market")],
    )
    services = load_service_scenario(
        path, boundary=_boundary(), categories={"health", "food"}
    )
    assert [(item.category, item.name) for item in services] == [
        ("health", "New clinic"),
        ("food", "Market"),
    ]
    assert services[0].point.equals(Point(0.009, 0.0))


@pytest.mark.parametrize(
    ("feature", "message"),
    [
        (_feature(category="university"), "unsupported or unselected"),
        (_feature(coords=(5.0, 0.0)), "outside the municipality"),
        (_feature(coords=(181.0, 0.0)), "outside WGS84"),
        (_feature(coords=(True, 0.0)), "numeric"),
        (
            {
                "type": "Feature",
                "properties": {"category": "health"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
            "Point geometry",
        ),
    ],
)
def test_scenario_rejects_invalid_features(tmp_path, feature, message):
    path = _scenario(tmp_path, [feature])
    with pytest.raises(ValueError, match=message):
        load_service_scenario(path, boundary=_boundary(), categories={"health", "food"})


def test_scenario_needs_nonempty_feature_collection(tmp_path):
    path = _scenario(tmp_path, [])
    with pytest.raises(ValueError, match="1 to 200"):
        load_service_scenario(path, boundary=_boundary(), categories={"health"})


def test_scenario_snapping_rejects_unrealistic_locations():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:3857"
    graph.add_node(1, x=0.0, y=0.0)
    result = snap_services_to_graph(
        graph,
        {"health": [("A", Point(0.001, 0.0))]},
        max_distance_m=250,
    )
    assert result.nodes_by_category == {"health": [1]}
    with pytest.raises(ValueError, match="from the walking network"):
        snap_services_to_graph(
            graph,
            {"health": [("B", Point(0.01, 0.0))]},
            max_distance_m=250,
        )


def test_scenario_reuses_graph_but_does_not_modify_original_services(tmp_path):
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:3857"
    for identifier, x in ((1, 0.0), (2, 500.0), (3, 1000.0)):
        graph.add_node(identifier, x=x, y=0.0)
    for left, right in ((1, 2), (2, 3)):
        graph.add_edge(left, right, travel_time=1200.0)
        graph.add_edge(right, left, travel_time=1200.0)

    region = Region({"city": "Test", "state": "Test", "country": "Brazil"})
    region._Region__graph = graph
    region._Region__services = {"health": [1], "food": [3]}
    region._service_categories = {"health": [], "food": []}
    region._boundary = _boundary()
    region.set_population_origins(
        OriginSet(
            strategy="population_grid",
            weight_unit="population",
            origins=(
                Origin("west", 1, 50.0),
                Origin("east", 3, 50.0),
            ),
        )
    )

    path = _scenario(tmp_path, [_feature()])
    original, simulated, added = region.simulate_services(path)
    assert original.population_report is not None
    assert simulated.population_report is not None
    assert original.population_report.categories["health"].coverage_percentage == 50
    assert simulated.population_report.categories["health"].coverage_percentage == 100
    assert original.population_report.overall_coverage_percentage == 0
    assert simulated.population_report.overall_coverage_percentage == 50
    assert region._Region__services == {"health": [1], "food": [3]}
    assert added[0]["category"] == "health"
    assert added[0]["graph_node_id"] == 3

    payload = format_simulation_output(
        original,
        simulated,
        locale=region.locale,
        output_mode="simple",
        services=added,
        scenario_path=path,
    )
    assert payload["mode"] == "hypothetical_services"
    assert payload["delta"]["unit"] == "percentage_points"
    assert payload["delta"]["population"]["category_coverage"]["health"] == 50
    assert payload["delta"]["population"]["overall_coverage"] == 50
    assert payload["baseline"]["overall_result"] == 0
    assert payload["simulated"]["overall_result"] == 50


def test_simulation_cannot_write_into_official_database(tmp_path):
    args = [
        "--city",
        "Test",
        "--pbf",
        "nonexistent.pbf",
        "--population-grid",
        "nonexistent.zip",
        "--simulate-services",
        "example.geojson",
        "--enable-db",
    ]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_cli_exposes_hypothetical_service_options():
    args = build_parser().parse_args(
        [
            "--city",
            "Test",
            "--pbf",
            "source.osm.pbf",
            "--population-grid",
            "grade.zip",
            "--simulate-services",
            "example.geojson",
            "--max-snap-distance-m",
            "400",
        ]
    )
    assert str(args.simulate_services) == "example.geojson"
    assert args.max_snap_distance_m == 400
