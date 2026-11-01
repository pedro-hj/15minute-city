from zipfile import ZipFile

import geopandas as gpd
import pytest
from shapely.geometry import box

from fifteen_minute_city.infrastructure.population_normalizer import (
    normalize_population_grid,
)


def _insee_grid(tmp_path):
    source = tmp_path / "insee.gpkg"
    gpd.GeoDataFrame(
        {
            "idcar_200m": ["west", "east", "empty"],
            "ind": [80.0, 20.0, 0.0],
            "i_est_200": [0, 1, 0],
            "geometry": [
                box(4.79, 45.72, 4.80, 45.73),
                box(4.89, 45.72, 4.90, 45.73),
                box(4.95, 45.72, 4.96, 45.73),
            ],
        },
        crs="EPSG:4326",
    ).to_file(source, driver="GPKG")
    return source


def test_insee_estimation_and_boundary(tmp_path):
    source = _insee_grid(tmp_path)
    boundary = tmp_path / "lyon.geojson"
    gpd.GeoDataFrame(
        {"geometry": [box(4.77, 45.70, 4.82, 45.75)]}, crs="EPSG:4326"
    ).to_file(boundary, driver="GeoJSON")
    target = tmp_path / "normalized.gpkg"
    metadata = normalize_population_grid(
        source, target, profile="insee-filosofi-2021", boundary=boundary
    )
    grid = gpd.read_file(target)
    assert len(grid) == 1
    assert grid.iloc[0]["grid_id"] == "west"
    assert grid.iloc[0]["population"] == 80
    assert grid.iloc[0]["estimated"] == 0
    assert grid.iloc[0]["country"] == "France"
    assert grid.iloc[0]["source_year"] == 2021
    assert metadata["total_population"] == 80
    assert metadata["source_crs"] == "EPSG:4326"
    assert target.with_suffix(".metadata.json").exists()
    assert grid.crs.to_epsg() == 4326


def test_boundary_filter_preserves_row_alignment(tmp_path):
    source = _insee_grid(tmp_path)
    boundary = tmp_path / "east.geojson"
    gpd.GeoDataFrame(
        {"geometry": [box(4.88, 45.71, 4.92, 45.74)]}, crs="EPSG:4326"
    ).to_file(boundary, driver="GeoJSON")
    target = tmp_path / "east.gpkg"
    normalize_population_grid(
        source, target, profile="insee-filosofi-2021", boundary=boundary
    )
    grid = gpd.read_file(target)
    assert len(grid) == 1
    assert grid.iloc[0]["grid_id"] == "east"
    assert grid.iloc[0]["population"] == 20
    assert grid.iloc[0]["estimated"] == 1
    assert grid.iloc[0]["longitude"] == pytest.approx(4.895)


def test_insee_projected_grid_is_reprojected_to_wgs84(tmp_path):
    source = _insee_grid(tmp_path)
    projected = tmp_path / "projected.gpkg"
    gpd.read_file(source).to_crs("EPSG:3035").to_file(projected, driver="GPKG")
    target = tmp_path / "wgs84.gpkg"
    metadata = normalize_population_grid(
        projected, target, profile="insee-filosofi-2021"
    )
    grid = gpd.read_file(target)
    assert grid.crs.to_epsg() == 4326
    assert grid.loc[0, "longitude"] == pytest.approx(4.795, abs=0.001)
    assert grid.loc[0, "latitude"] == pytest.approx(45.725, abs=0.001)
    assert metadata["source_crs"] == "EPSG:3035"


def test_insee_estimates_are_reported(tmp_path):
    source = _insee_grid(tmp_path)
    target = tmp_path / "normalized.gpkg"
    metadata = normalize_population_grid(source, target, profile="insee-filosofi-2021")
    assert metadata["cells"] == 2
    assert metadata["zero_population_cells_removed"] == 1
    assert metadata["estimated_cells"] == 1
    assert metadata["population_in_flagged_cells"] == 20
    assert metadata["total_population"] == 100


def test_ibge_zip_is_supported(tmp_path):
    shape = tmp_path / "shape"
    shape.mkdir()
    shp = shape / "grade.shp"
    gpd.GeoDataFrame(
        {
            "ID_UNICO": ["br-01", "br-02"],
            "TOTAL": [25, 75],
            "geometry": [
                box(-46.001, -24.001, -45.999, -23.999),
                box(-45.991, -24.001, -45.989, -23.999),
            ],
        },
        crs="EPSG:4326",
    ).to_file(shp)
    source = tmp_path / "ibge.zip"
    with ZipFile(source, "w") as zip_file:
        for part in shape.iterdir():
            zip_file.write(part, arcname=part.name)
    target = tmp_path / "normalized.gpkg"
    metadata = normalize_population_grid(source, target, profile="ibge")
    assert metadata["country"] == "Brazil"
    assert metadata["unknown_estimation_cells"] == 2
    assert gpd.read_file(target)["population"].sum() == 100


def test_zip_multi_geography_requires_explicit_member(tmp_path):
    source = _insee_grid(tmp_path)
    archive = tmp_path / "france.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.write(source, arcname="metro/insee.gpkg")
        zip_file.write(source, arcname="reunion/insee.gpkg")
    with pytest.raises(ValueError, match="--zip-member"):
        normalize_population_grid(
            archive, tmp_path / "normalized.gpkg", profile="insee-filosofi-2021"
        )
    metadata = normalize_population_grid(
        archive,
        tmp_path / "normalized.gpkg",
        profile="insee-filosofi-2021",
        zip_member="metro/insee.gpkg",
    )
    assert metadata["cells"] == 2


@pytest.mark.parametrize(
    ("values", "error"),
    [([-1, 5], "must not be negative"), ([float("nan"), 5], "finite and numeric")],
)
def test_invalid_population_is_rejected(tmp_path, values, error):
    source = tmp_path / "custom.geojson"
    gpd.GeoDataFrame(
        {
            "cell": ["a", "b"],
            "head_count": values,
            "geometry": [box(0, 0, 1, 1), box(1, 0, 2, 1)],
        },
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")
    with pytest.raises(ValueError, match=error):
        normalize_population_grid(
            source,
            tmp_path / "out.gpkg",
            profile="custom",
            country="X",
            population_column="head_count",
            id_column="cell",
        )


def test_output_is_not_overwritten_by_default(tmp_path):
    source = _insee_grid(tmp_path)
    target = tmp_path / "normalized.gpkg"
    normalize_population_grid(source, target, profile="insee-filosofi-2021")
    with pytest.raises(FileExistsError):
        normalize_population_grid(source, target, profile="insee-filosofi-2021")
