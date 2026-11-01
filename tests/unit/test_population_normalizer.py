"""Tests for the simple, country-independent population normalizer."""

import sqlite3

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import box

from fifteen_minute_city.infrastructure.origins import load_population_grid
from fifteen_minute_city.infrastructure.population_normalizer import main, normalize


def make_grid(
    tmp_path,
    id_col="idcar_200m",
    pop_col="ind",
    crs="EPSG:2154",
    extension="gpkg",
):
    source = tmp_path / f"source.{extension}"
    cells = gpd.GeoDataFrame(
        {
            id_col: ["001", "002", "003"],
            pop_col: [10, 2.5, 0],
            "geometry": [
                box(4.79, 45.72, 4.80, 45.73),
                box(4.89, 45.72, 4.90, 45.73),
                box(4.95, 45.72, 4.96, 45.73),
            ],
        },
        crs="EPSG:4326",
    ).to_crs(crs)
    cells.to_file(source)
    return source


@pytest.mark.parametrize(
    "id_col,pop_col,crs,extension",
    [
        ("idcar_200m", "ind", "EPSG:2154", "shp"),
        ("ibge_id", "habitantes", "EPSG:4674", "gpkg"),
    ],
)
def test_normalizes_french_and_brazilian_grids(
    tmp_path, id_col, pop_col, crs, extension
):
    source = make_grid(tmp_path, id_col, pop_col, crs, extension)
    output = tmp_path / "normalized" / "population.gpkg"
    normalized = normalize(source, id_col, pop_col, output)
    saved = gpd.read_file(output)

    assert list(normalized.columns) == ["ID", "POPULATION", "LOCATION"]
    assert list(saved.columns) == ["ID", "POPULATION", "geometry"]
    assert saved.crs.to_string() == crs
    assert saved["ID"].tolist() == ["001", "002", "003"]
    assert saved["POPULATION"].tolist() == [10, 2.5, 0]
    with sqlite3.connect(output) as db:
        column = db.execute(
            "SELECT column_name FROM gpkg_geometry_columns"
        ).fetchone()
    assert column == ("LOCATION",)


def test_cli_returns_success_and_produces_file(tmp_path, capsys):
    source = make_grid(tmp_path)
    output = tmp_path / "out.gpkg"
    assert (
        main(
            [
                "--input",
                str(source),
                "--output",
                str(output),
                "--id-column",
                "idcar_200m",
                "--population-column",
                "ind",
            ]
        )
        == 0
    )
    assert "Normalized 3 records" in capsys.readouterr().out
    assert len(gpd.read_file(output)) == 3


def test_normalized_grid_is_accepted_by_main_loader(tmp_path):
    source = make_grid(tmp_path)
    output = tmp_path / "out.gpkg"
    normalize(source, "idcar_200m", "ind", output)

    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(10, x=4.795, y=45.725)
    graph.add_node(20, x=4.895, y=45.725)
    graph.add_edge(10, 20, travel_time=60.0)
    graph.add_edge(20, 10, travel_time=60.0)
    boundary = gpd.GeoDataFrame(
        geometry=[box(4.79, 45.71, 4.81, 45.74)],
        crs="EPSG:4326",
    )

    origins = load_population_grid(
        output,
        graph,
        population_column="POPULATION",
        id_column="ID",
        boundary=boundary,
    )
    assert origins.total_weight == 10
    assert len(origins.origins) == 1
    assert origins.origins[0].origin_id == "grid:001"


@pytest.mark.parametrize(
    "change,message",
    [
        ("no_id", "Invalid column"),
        ("no_population", "Invalid column"),
        ("negative", "negative"),
        ("missing_population", "finite"),
        ("infinite_population", "finite"),
        ("empty_id", "nonempty"),
        ("duplicate_id", "unique"),
        ("empty_geometry", "nonempty geometry"),
    ],
)
def test_rejects_invalid_input(tmp_path, change, message):
    source = make_grid(tmp_path)
    ids, people = "idcar_200m", "ind"
    if change not in ("no_id", "no_population"):
        grid = gpd.read_file(source)
        if change == "negative":
            grid.loc[0, people] = -1
        elif change == "missing_population":
            grid.loc[0, people] = None
        elif change == "infinite_population":
            grid.loc[0, people] = float("inf")
        elif change == "empty_id":
            grid.loc[0, ids] = " "
        elif change == "duplicate_id":
            grid.loc[0, ids] = "002"
        elif change == "empty_geometry":
            grid.loc[0, "geometry"] = None
        grid.to_file(source)
    if change == "no_id":
        ids = "missing"
    if change == "no_population":
        people = "missing"

    with pytest.raises(ValueError, match=message):
        normalize(source, ids, people, tmp_path / "out.gpkg")
    assert not (tmp_path / "out.gpkg").exists()


def test_does_not_overwrite_output_or_source(tmp_path):
    source = make_grid(tmp_path)
    with pytest.raises(ValueError, match="different"):
        normalize(source, "idcar_200m", "ind", source)
    output = tmp_path / "out.gpkg"
    normalize(source, "idcar_200m", "ind", output)
    with pytest.raises(FileExistsError, match="already exists"):
        normalize(source, "idcar_200m", "ind", output)
