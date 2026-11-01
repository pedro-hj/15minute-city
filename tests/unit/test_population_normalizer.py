import sqlite3
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from fifteen_minute_city.infrastructure import population_normalizer
from fifteen_minute_city.infrastructure.population_normalizer import (
    normalize_population_grid,
)


def _grid(tmp_path, *, population_col="ind", id_col="idcar_200m"):
    source = tmp_path / "grid.gpkg"
    gpd.GeoDataFrame(
        {
            id_col: ["west", "east", "empty"],
            population_col: [80.0, 20.0, 0.0],
            "geometry": [
                box(4.79, 45.72, 4.80, 45.73),
                box(4.89, 45.72, 4.90, 45.73),
                box(4.95, 45.72, 4.96, 45.73),
            ],
        },
        crs="EPSG:4326",
    ).to_file(source, driver="GPKG")
    return source


def test_exact_three_fields_and_geometry_name_in_geopackage(tmp_path):
    source = _grid(tmp_path)
    output = tmp_path / "normalizado.gpkg"
    metadata = normalize_population_grid(source, output)

    with sqlite3.connect(output) as connection:
        cols = connection.execute(
            "SELECT column_name FROM gpkg_geometry_columns"
        ).fetchall()
        table = connection.execute("PRAGMA table_info(grade_populacional)").fetchall()
    assert cols == [("LOCALIZACAO",)]
    assert {row[1] for row in table} == {"fid", "LOCALIZACAO", "ID", "POPULACAO"}

    # GeoPandas uses the conventional attribute 'geometry' when reading GPKG.
    grid = gpd.read_file(output)
    assert set(grid.columns) == {"ID", "POPULACAO", "geometry"}
    assert grid.crs.to_epsg() == 4326
    assert grid["ID"].tolist() == ["west", "east", "empty"]
    assert grid["POPULACAO"].tolist() == [80.0, 20.0, 0.0]
    assert metadata["fields"] == ["ID", "LOCALIZACAO", "POPULACAO"]
    assert metadata["total_population"] == 100.0
    assert metadata["zero_population_cells"] == 1
    assert output.with_suffix(".metadata.json").exists()


def test_ibge_field_names_are_generic_aliases(tmp_path):
    source = _grid(tmp_path, population_col="TOTAL", id_col="ID_UNICO")
    report = normalize_population_grid(source, tmp_path / "ibge.gpkg")
    assert report["source_id_column"] == "ID_UNICO"
    assert report["source_population_column"] == "TOTAL"


def test_city_geocodes_without_country_or_boundary(tmp_path, monkeypatch):
    calls = []

    def fake_geocode(place):
        calls.append(place)
        return gpd.GeoDataFrame(
            {"geometry": [box(4.77, 45.70, 4.82, 45.75)]},
            crs="EPSG:4326",
        )

    monkeypatch.setattr(population_normalizer.ox, "geocode_to_gdf", fake_geocode)
    output = tmp_path / "lyon.gpkg"
    report = normalize_population_grid(_grid(tmp_path), output, city="Lyon")
    assert calls == [{"city": "Lyon"}]
    assert report["boundary"].startswith("geocoded:")
    assert gpd.read_file(output)["ID"].tolist() == ["west"]


def test_optional_country_and_state_disambiguate_city(tmp_path, monkeypatch):
    seen = []

    def fake_geocode(place):
        seen.append(place)
        return gpd.GeoDataFrame(
            {"geometry": [box(4.77, 45.70, 4.82, 45.75)]},
            crs="EPSG:4326",
        )

    monkeypatch.setattr(population_normalizer.ox, "geocode_to_gdf", fake_geocode)
    normalize_population_grid(
        _grid(tmp_path),
        tmp_path / "lyon.gpkg",
        city="Lyon",
        state="Auvergne-Rhone-Alpes",
        country="France",
    )
    assert seen == [
        {
            "city": "Lyon",
            "state": "Auvergne-Rhone-Alpes",
            "country": "France",
        }
    ]


def test_manual_boundary_keeps_only_selected_centers(tmp_path):
    area = tmp_path / "boundary.geojson"
    gpd.GeoDataFrame(
        {"geometry": [box(4.88, 45.70, 4.92, 45.75)]}, crs="EPSG:4326"
    ).to_file(area, driver="GeoJSON")
    output = tmp_path / "east.gpkg"
    normalize_population_grid(_grid(tmp_path), output, boundary=area)
    assert gpd.read_file(output)["ID"].tolist() == ["east"]


def test_projected_source_is_reprojected(tmp_path):
    source = _grid(tmp_path)
    projected = tmp_path / "projected.gpkg"
    gpd.read_file(source).to_crs("EPSG:3035").to_file(projected, driver="GPKG")
    output = tmp_path / "output.gpkg"
    report = normalize_population_grid(projected, output)
    assert gpd.read_file(output).crs.to_epsg() == 4326
    assert report["source_crs"] == "EPSG:3035"


def test_zip_shapefile_source(tmp_path):
    shape_folder = tmp_path / "shapefile"
    shape_folder.mkdir()
    shapefile = shape_folder / "grid.shp"
    gpd.GeoDataFrame(
        {
            "ID_UNICO": ["a", "b"],
            "TOTAL": [11, 19],
            "geometry": [box(1, 1, 2, 2), box(2, 1, 3, 2)],
        },
        crs="EPSG:4326",
    ).to_file(shapefile, driver="ESRI Shapefile")
    archive = tmp_path / "input.zip"
    with ZipFile(archive, "w") as zipper:
        for file in shape_folder.iterdir():
            zipper.write(file, arcname=file.name)
    output = tmp_path / "output.gpkg"
    normalize_population_grid(archive, output)
    assert gpd.read_file(output)["POPULACAO"].sum() == 30


def test_zip_multiple_sources_needs_member(tmp_path):
    source = _grid(tmp_path)
    archive = tmp_path / "two.zip"
    with ZipFile(archive, "w") as zipper:
        zipper.write(source, arcname="one.gpkg")
        zipper.write(source, arcname="two.gpkg")
    with pytest.raises(ValueError, match="--zip-member"):
        normalize_population_grid(archive, tmp_path / "out.gpkg")
    normalize_population_grid(archive, tmp_path / "out.gpkg", zip_member="one.gpkg")
    assert len(gpd.read_file(tmp_path / "out.gpkg")) == 3


def test_csv_with_latitude_longitude(tmp_path):
    source = tmp_path / "points.csv"
    pd.DataFrame(
        {
            "CELL_CODE": ["001", "002"],
            "RESIDENTES": [12, 18],
            "latitude": [-23.96, -23.97],
            "longitude": [-46.33, -46.32],
        }
    ).to_csv(source, index=False)
    output = tmp_path / "output.gpkg"
    normalize_population_grid(source, output)
    grid = gpd.read_file(output)
    assert grid["ID"].tolist() == ["001", "002"]
    assert grid["POPULACAO"].sum() == 30
    assert all(grid.geometry.geom_type == "Point")


def test_csv_with_wkt_geometry_and_crs(tmp_path):
    source = tmp_path / "polygons.csv"
    pd.DataFrame(
        {
            "ID": ["ABC"],
            "POPULATION": [7],
            "WKT": ["POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))"],
        }
    ).to_csv(source, index=False)
    with pytest.raises(ValueError, match="--input-crs"):
        normalize_population_grid(source, tmp_path / "out.gpkg")
    normalize_population_grid(source, tmp_path / "out.gpkg", input_crs="EPSG:4326")
    assert gpd.read_file(tmp_path / "out.gpkg").geometry.iloc[0].geom_type == "Polygon"


def test_generates_technical_id_when_missing(tmp_path):
    source = tmp_path / "no_id.geojson"
    gpd.GeoDataFrame(
        {"population": [10], "geometry": [box(0, 0, 1, 1)]},
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")
    report = normalize_population_grid(source, tmp_path / "out.gpkg")
    assert report["generated_ids"] is True
    assert gpd.read_file(tmp_path / "out.gpkg")["ID"].tolist() == ["cell-00000001"]


def test_unknown_column_requires_explicit_mapping(tmp_path):
    source = tmp_path / "unknown.geojson"
    gpd.GeoDataFrame(
        {"cell": ["A"], "qty_people": [14], "geometry": [box(0, 0, 1, 1)]},
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")
    with pytest.raises(ValueError, match="--population-column"):
        normalize_population_grid(source, tmp_path / "out.gpkg")
    report = normalize_population_grid(
        source,
        tmp_path / "out.gpkg",
        id_column="cell",
        population_column="qty_people",
    )
    assert report["total_population"] == 14


def test_ambiguous_population_columns_require_override(tmp_path):
    source = tmp_path / "ambiguous.geojson"
    gpd.GeoDataFrame(
        {
            "ID": ["a"],
            "POP": [1],
            "TOTAL": [3],
            "geometry": [box(0, 0, 1, 1)],
        },
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")
    with pytest.raises(ValueError, match="--population-column"):
        normalize_population_grid(source, tmp_path / "out.gpkg")
    normalize_population_grid(source, tmp_path / "out.gpkg", population_column="TOTAL")
    assert gpd.read_file(tmp_path / "out.gpkg")["POPULACAO"].sum() == 3


def test_negative_population_is_rejected(tmp_path):
    source = tmp_path / "bad.geojson"
    gpd.GeoDataFrame(
        {"ID": ["a"], "population": [-1], "geometry": [box(0, 0, 1, 1)]},
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")
    with pytest.raises(ValueError, match="negative"):
        normalize_population_grid(source, tmp_path / "out.gpkg")


def test_duplicate_ids_are_rejected(tmp_path):
    source = tmp_path / "duplicates.geojson"
    gpd.GeoDataFrame(
        {
            "ID": ["same", "same"],
            "population": [1, 2],
            "geometry": [box(0, 0, 1, 1), box(2, 0, 3, 1)],
        },
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")
    with pytest.raises(ValueError, match="unique"):
        normalize_population_grid(source, tmp_path / "out.gpkg")


def test_prevents_accidental_overwriting(tmp_path):
    source = _grid(tmp_path)
    output = tmp_path / "out.gpkg"
    normalize_population_grid(source, output)
    with pytest.raises(FileExistsError):
        normalize_population_grid(source, output)


def test_cannot_mix_city_and_boundary(tmp_path):
    source = _grid(tmp_path)
    with pytest.raises(ValueError, match="either --boundary or --city"):
        normalize_population_grid(
            source, tmp_path / "out.gpkg", city="Lyon", boundary=source
        )
