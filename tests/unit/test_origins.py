from zipfile import ZipFile

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import Point, box

from fifteen_minute_city.infrastructure.origins import (
    load_population_grid,
    origins_from_graph_nodes,
)


def _graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(10, x=-46.0, y=-24.0)
    graph.add_node(20, x=-45.99, y=-24.0)
    graph.add_edge(10, 20, travel_time=60.0)
    graph.add_edge(20, 10, travel_time=60.0)
    return graph


def test_population_grid_is_snapped_and_zero_population_cells_are_ignored(tmp_path):
    grid_path = tmp_path / "population.geojson"
    grid = gpd.GeoDataFrame(
        {
            "cell_id": ["west", "east", "empty"],
            "population": [80, 20, 0],
            "geometry": [
                box(-46.001, -24.001, -45.999, -23.999),
                box(-45.991, -24.001, -45.989, -23.999),
                Point(-45.995, -24.0),
            ],
        },
        crs="EPSG:4326",
    )
    grid.to_file(grid_path, driver="GeoJSON")

    origins = load_population_grid(
        grid_path,
        _graph(),
        population_column="population",
        id_column="cell_id",
    )

    assert origins.strategy == "population_grid"
    assert origins.total_weight == 100
    assert origins.metadata["positive_population_feature_count"] == 2
    assert [
        (item.origin_id, item.node_id, item.weight) for item in origins.origins
    ] == [
        ("grid:west", 10, 80.0),
        ("grid:east", 20, 20.0),
    ]


def test_negative_population_is_rejected(tmp_path):
    grid_path = tmp_path / "invalid.geojson"
    gpd.GeoDataFrame(
        {"population": [-1], "geometry": [Point(-46, -24)]},
        crs="EPSG:4326",
    ).to_file(grid_path, driver="GeoJSON")

    with pytest.raises(ValueError, match="must not be negative"):
        load_population_grid(grid_path, _graph())


def test_ibge_zip_is_automatically_filtered_by_municipality(tmp_path):
    shapefile_dir = tmp_path / "shape"
    shapefile_dir.mkdir()
    shapefile_path = shapefile_dir / "grade_test.shp"
    gpd.GeoDataFrame(
        {
            "ID_UNICO": ["west", "east"],
            "TOTAL": [80, 20],
            "geometry": [
                box(-46.001, -24.001, -45.999, -23.999),
                box(-45.991, -24.001, -45.989, -23.999),
            ],
        },
        crs="EPSG:4326",
    ).to_file(shapefile_path)
    archive_path = tmp_path / "grade_test.zip"
    with ZipFile(archive_path, "w") as archive:
        for component in shapefile_dir.iterdir():
            archive.write(component, arcname=component.name)

    boundary = gpd.GeoDataFrame(
        {"geometry": [box(-46.002, -24.002, -45.997, -23.998)]},
        crs="EPSG:4326",
    ).to_crs("EPSG:3857")
    origins = load_population_grid(
        archive_path,
        _graph(),
        population_column="TOTAL",
        id_column="ID_UNICO",
        boundary=boundary,
    )

    assert origins.total_weight == 80
    assert [origin.origin_id for origin in origins.origins] == ["grid:west"]
    assert origins.metadata["spatially_filtered"] is True
    assert origins.metadata["municipality_feature_count"] == 1


def test_population_grid_without_municipal_intersection_is_rejected(tmp_path):
    grid_path = tmp_path / "population.geojson"
    gpd.GeoDataFrame(
        {"population": [10], "geometry": [Point(-46, -24)]},
        crs="EPSG:4326",
    ).to_file(grid_path, driver="GeoJSON")
    boundary = gpd.GeoDataFrame(
        {"geometry": [box(-40, -20, -39, -19)]},
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="does not intersect"):
        load_population_grid(grid_path, _graph(), boundary=boundary)


def test_graph_node_origins_use_unit_weights():
    origins = origins_from_graph_nodes(_graph())

    assert origins.strategy == "network_nodes"
    assert origins.weight_unit == "node_count"
    assert origins.total_weight == 2
