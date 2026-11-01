import sqlite3
from zipfile import ZipFile

import geopandas as gpd
import networkx as nx
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon, box

from fifteen_minute_city.infrastructure import population_normalizer
from fifteen_minute_city.infrastructure.origins import load_population_grid
from fifteen_minute_city.infrastructure.population_normalizer import (
    main,
    normalize_population_grid,
)


def _grid(tmp_path, *, population_col="people", id_col="code", crs="EPSG:4326"):
    source = tmp_path / "grid.gpkg"
    gpd.GeoDataFrame(
        {
            id_col: ["001", "002", "003"],
            population_col: [80.5, 20.0, 0.0],
            "geometry": [
                box(4.79, 45.72, 4.80, 45.73),
                box(4.89, 45.72, 4.90, 45.73),
                box(4.95, 45.72, 4.96, 45.73),
            ],
        },
        crs="EPSG:4326",
    ).to_crs(crs).to_file(source, driver="GPKG", layer="cells")
    return source


def _normalize(source, output, **options):
    """Map the two fields used by this module's default fixture."""
    return normalize_population_grid(
        source, output, id_column="code", population_column="people", **options
    )


@pytest.mark.parametrize(
    ("id_col", "population_col", "crs"),
    [
        ("ID_UNICO", "TOTAL", "EPSG:4674"),
        ("idcar_200m", "ind", "EPSG:3035"),
        ("arbitrary_key", "arbitrary_count", "EPSG:4326"),
    ],
)
def test_explicit_mapping_produces_same_contract(tmp_path, id_col, population_col, crs):
    source = _grid(tmp_path, id_col=id_col, population_col=population_col, crs=crs)
    output = tmp_path / "normalizado.gpkg"
    report = normalize_population_grid(
        source,
        output,
        id_column=id_col,
        population_column=population_col,
        location_column="geom",
    )
    with sqlite3.connect(output) as connection:
        assert connection.execute(
            "SELECT column_name FROM gpkg_geometry_columns"
        ).fetchall() == [("LOCALIZACAO",)]
        columns = connection.execute("PRAGMA table_info(grade_populacional)").fetchall()
    assert {row[1] for row in columns} == {"fid", "ID", "LOCALIZACAO", "POPULACAO"}
    grid = gpd.read_file(output)
    assert set(grid.columns) == {"ID", "POPULACAO", "geometry"}
    assert grid.crs.to_epsg() == 4326
    assert grid["ID"].tolist() == ["001", "002", "003"]
    assert grid["POPULACAO"].tolist() == [80.5, 20.0, 0.0]
    assert report["source_crs"] == crs
    assert report["total_population"] == 100.5
    assert report["zero_population_cells"] == 1
    assert output.with_suffix(".metadata.json").is_file()


def test_shapefile_zip_with_nested_member(tmp_path):
    folder = tmp_path / "shape"
    folder.mkdir()
    gpd.read_file(_grid(tmp_path)).to_file(folder / "cells.shp")
    archive = tmp_path / "input.zip"
    with ZipFile(archive, "w") as zipper:
        for file in folder.iterdir():
            zipper.write(file, arcname=f"nested/{file.name}")
    output = tmp_path / "out.gpkg"
    _normalize(archive, output, location_column="geometry")
    assert gpd.read_file(output)["POPULACAO"].sum() == 100.5


def test_zip_multiple_sources_requires_member(tmp_path):
    source = _grid(tmp_path)
    archive = tmp_path / "two.zip"
    with ZipFile(archive, "w") as zipper:
        zipper.write(source, arcname="one.gpkg")
        zipper.write(source, arcname="two.gpkg")
    with pytest.raises(ValueError, match="--zip-member"):
        _normalize(archive, tmp_path / "out.gpkg")
    _normalize(archive, tmp_path / "out.gpkg", zip_member="one.gpkg")
    assert len(gpd.read_file(tmp_path / "out.gpkg")) == 3


def test_multiple_layers_requires_explicit_choice(tmp_path):
    source = _grid(tmp_path)
    grid = gpd.read_file(source)
    grid["people"] = 1
    grid.to_file(source, layer="other", driver="GPKG")
    with pytest.raises(ValueError, match="--layer"):
        _normalize(source, tmp_path / "out.gpkg")
    report = _normalize(source, tmp_path / "out.gpkg", layer="other")
    assert report["total_population"] == 3


def test_vector_rejects_incorrect_location_mapping(tmp_path):
    with pytest.raises(ValueError, match="not the spatial column"):
        _normalize(_grid(tmp_path), tmp_path / "out.gpkg", location_column="people")


@pytest.mark.parametrize("compressed", [False, True])
def test_csv_explicit_coordinates_preserve_ids(tmp_path, compressed):
    source = tmp_path / "points.csv"
    pd.DataFrame(
        {
            "code": ["001", "NA"],
            "people": [12, 18],
            "north": [-23.96, -23.97],
            "east": [-46.33, -46.32],
        }
    ).to_csv(source, index=False)
    if compressed:
        archive = tmp_path / "csv.zip"
        with ZipFile(archive, "w") as zipper:
            zipper.write(source, arcname="points.csv")
        source = archive
    output = tmp_path / "out.gpkg"
    _normalize(source, output, latitude_column="north", longitude_column="east")
    grid = gpd.read_file(output)
    assert grid["ID"].tolist() == ["001", "NA"]
    assert grid["POPULACAO"].sum() == 30
    assert grid.geometry.iloc[0].equals(Point(-46.33, -23.96))


def test_csv_wkt_requires_location_and_crs(tmp_path):
    source = tmp_path / "polygons.csv"
    pd.DataFrame(
        {
            "code": ["A"],
            "people": [7],
            "shape": ["POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))"],
        }
    ).to_csv(source, index=False)
    output = tmp_path / "out.gpkg"
    with pytest.raises(ValueError, match="CSV requires --location-column"):
        _normalize(source, output)
    with pytest.raises(ValueError, match="--input-crs"):
        _normalize(source, output, location_column="shape")
    _normalize(source, output, location_column="shape", input_crs="EPSG:4326")
    assert gpd.read_file(output).geometry.iloc[0].geom_type == "Polygon"


@pytest.mark.parametrize("column", ["code", "people"])
def test_missing_mapped_column_is_not_inferred(tmp_path, column):
    source = _grid(tmp_path)
    grid = gpd.read_file(source).rename(
        columns={column: "ID_UNICO" if column == "code" else "TOTAL"}
    )
    grid.to_file(source, layer="cells", driver="GPKG")
    with pytest.raises(ValueError, match="not found; available columns"):
        _normalize(source, tmp_path / "out.gpkg")


@pytest.mark.parametrize("missing", ["--id-column", "--population-column"])
def test_cli_requires_mapping(missing, tmp_path, capsys):
    args = ["--input", "input.gpkg", "--output", str(tmp_path / "out.gpkg")]
    args += (
        ["--population-column", "TOTAL"]
        if missing == "--id-column"
        else ["--id-column", "ID_UNICO"]
    )
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert missing in capsys.readouterr().err


def test_cli_output_is_consumable_by_main_loader(tmp_path):
    output = tmp_path / "out.gpkg"
    assert (
        main(
            [
                "--input",
                str(_grid(tmp_path)),
                "--output",
                str(output),
                "--id-column",
                "code",
                "--location-column",
                "geom",
                "--population-column",
                "people",
            ]
        )
        == 0
    )
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(10, x=4.795, y=45.725)
    graph.add_node(20, x=4.895, y=45.725)
    graph.add_edge(10, 20, travel_time=60.0)
    graph.add_edge(20, 10, travel_time=60.0)
    origins = load_population_grid(
        output, graph, id_column="ID", population_column="POPULACAO"
    )
    assert origins.total_weight == 100.5
    assert [(o.origin_id, o.node_id) for o in origins.origins] == [
        ("grid:001", 10),
        ("grid:002", 20),
    ]


@pytest.mark.parametrize(
    ("field", "values", "message"),
    [
        ("people", [-1, 20, 0], "negative"),
        ("people", [float("inf"), 20, 0], "finite numeric"),
        ("people", [None, 20, 0], "finite numeric"),
        ("code", ["same", "same", "last"], "unique"),
        ("code", [None, "two", "three"], "null or empty"),
        ("code", [" ", "two", "three"], "null or empty"),
    ],
)
def test_invalid_population_and_ids_fail_before_writing(
    tmp_path, field, values, message
):
    source = _grid(tmp_path)
    grid = gpd.read_file(source)
    grid[field] = values
    grid.to_file(source, layer="cells", driver="GPKG")
    output = tmp_path / "out.gpkg"
    with pytest.raises(ValueError, match=message):
        _normalize(source, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        Point(),
        LineString([(0, 0), (1, 1)]),
        Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)]),
        Point(200, 20),
    ],
)
def test_invalid_locations_are_rejected(tmp_path, geometry):
    source = tmp_path / "bad.gpkg"
    gpd.GeoDataFrame(
        {"code": ["A"], "people": [10]}, geometry=[geometry], crs="EPSG:4326"
    ).to_file(source)
    with pytest.raises(ValueError):
        _normalize(source, tmp_path / "out.gpkg")


def test_optional_city_crop_uses_supplied_disambiguation(tmp_path, monkeypatch):
    calls = []

    def geocode(place):
        calls.append(place)
        return gpd.GeoDataFrame(
            geometry=[box(4.77, 45.70, 4.82, 45.75)], crs="EPSG:4326"
        )

    monkeypatch.setattr(population_normalizer.ox, "geocode_to_gdf", geocode)
    output = tmp_path / "out.gpkg"
    _normalize(_grid(tmp_path), output, city="Lyon", country="France")
    assert calls == [{"city": "Lyon", "country": "France"}]
    assert gpd.read_file(output)["ID"].tolist() == ["001"]


def test_local_boundary_and_overwrite(tmp_path):
    source = _grid(tmp_path)
    boundary = tmp_path / "boundary.geojson"
    gpd.GeoDataFrame(geometry=[box(4.88, 45.70, 4.92, 45.75)], crs="EPSG:4326").to_crs(
        "EPSG:3857"
    ).to_file(boundary)
    output = tmp_path / "out.gpkg"
    _normalize(source, output, boundary=boundary)
    assert gpd.read_file(output)["ID"].tolist() == ["002"]
    with pytest.raises(FileExistsError):
        _normalize(source, output)
    _normalize(source, output, overwrite=True)
    assert len(gpd.read_file(output)) == 3
    with pytest.raises(ValueError, match="either --boundary or --city"):
        _normalize(source, tmp_path / "other.gpkg", city="Lyon", boundary=boundary)


def test_missing_vector_crs_can_be_declared_without_overriding_known_crs(tmp_path):
    source = _grid(tmp_path)
    with pytest.raises(ValueError):
        _normalize(source, tmp_path / "conflict.gpkg", input_crs="EPSG:3857")
    shape = tmp_path / "no_crs.shp"
    gpd.read_file(source).to_file(shape)
    shape.with_suffix(".prj").unlink()
    with pytest.raises(ValueError, match="lacks a CRS"):
        _normalize(shape, tmp_path / "out.gpkg")
    _normalize(shape, tmp_path / "out.gpkg", input_crs="EPSG:4326")
    assert gpd.read_file(tmp_path / "out.gpkg").crs.to_epsg() == 4326


def test_malformed_csv_wkt_is_a_clear_cli_error(tmp_path, capsys):
    source = tmp_path / "bad.csv"
    source.write_text("code,people,shape\nA,10,not-a-geometry\n")
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--input",
                str(source),
                "--output",
                str(tmp_path / "out.gpkg"),
                "--id-column",
                "code",
                "--population-column",
                "people",
                "--location-column",
                "shape",
                "--input-crs",
                "EPSG:4326",
            ]
        )
    assert error.value.code == 2
    assert "invalid WKT geometry" in capsys.readouterr().err
