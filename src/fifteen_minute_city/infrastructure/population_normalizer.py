"""Normalize spatial population grids to ID, LOCALIZACAO and POPULACAO.

Institution and country independent. LOCALIZACAO is the spatial geometry
(polygon or point), not a text label. All output geometry uses WGS84.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.errors import GEOSException

_VECTOR_EXTENSIONS = {".gpkg", ".shp", ".geojson", ".json"}
_SUPPORTED_EXTENSIONS = _VECTOR_EXTENSIONS | {".csv"}


def _require_column(columns: list[str], name: str, option: str) -> str:
    """Use the supplied mapping exactly; never infer statistical meaning."""
    if name not in columns:
        raise ValueError(
            f"{option}='{name}' not found; available columns: {', '.join(columns)}"
        )
    return name


def _source(path: Path, zip_member: str | None) -> tuple[str, str, str | None]:
    if not path.is_file():
        raise FileNotFoundError(f"input not found: {path}")
    if path.suffix.lower() != ".zip":
        if zip_member is not None:
            raise ValueError("--zip-member only applies to ZIP input")
        ext = path.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            raise ValueError("unsupported format: use GPKG, SHP, GeoJSON, CSV or ZIP")
        return str(path), ext, None

    with ZipFile(path) as archive:
        entries = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and Path(name).suffix.lower() in _SUPPORTED_EXTENSIONS
        ]
    if zip_member is None:
        if len(entries) != 1:
            raise ValueError(
                "ZIP contains multiple spatial/tabular sources; use --zip-member"
            )
        zip_member = entries[0]
    if zip_member not in entries:
        raise ValueError(f"ZIP member not found: {zip_member}")
    ext = Path(zip_member).suffix.lower()
    return f"zip://{path}!{zip_member}", ext, zip_member


def _read_input(
    path: Path,
    source: str,
    ext: str,
    member: str | None,
    *,
    layer: str | None,
    input_crs: str | None,
    id_column: str,
    population_column: str,
    location_column: str | None,
    latitude_column: str | None,
    longitude_column: str | None,
) -> gpd.GeoDataFrame:
    if ext != ".csv":
        if latitude_column is not None or longitude_column is not None:
            raise ValueError("latitude/longitude options only apply to CSV")
        layers = pyogrio.list_layers(source)
        if layer is None and len(layers) != 1:
            names = ", ".join(str(item[0]) for item in layers)
            raise ValueError(f"input contains multiple layers; use --layer: {names}")
        options = {"layer": layer} if layer else {}
        info = pyogrio.read_info(source, **options)
        geometry_name = info.get("geometry_name") or "geometry"
        if location_column is not None and location_column not in {
            "geometry",
            geometry_name,
        }:
            raise ValueError(
                f"--location-column='{location_column}' is not the spatial column; "
                f"use '{geometry_name}' (or 'geometry')"
            )
        source_crs = info["crs"]
        if source_crs is None and input_crs is None:
            raise ValueError("input grid lacks a CRS; provide --input-crs")
        # Read only the requested indicators, avoiding unnecessary memory use.
        fields = list(info["fields"])
        _require_column(fields, id_column, "--id-column")
        _require_column(fields, population_column, "--population-column")
        options["columns"] = [id_column, population_column]
        grid = gpd.read_file(source, **options)
        if input_crs is not None:
            # Reject a conflicting CRS instead of silently changing coordinates.
            grid = grid.set_crs(input_crs)
        return grid

    if layer is not None:
        raise ValueError("--layer only applies to spatial formats")
    if member is not None:
        with ZipFile(path) as archive, archive.open(member) as data:
            table = pd.read_csv(data, dtype=str, keep_default_na=False)
    else:
        table = pd.read_csv(path, dtype=str, keep_default_na=False)
    columns = list(table.columns)

    if location_column is not None:
        if latitude_column is not None or longitude_column is not None:
            raise ValueError("use WKT geometry or latitude/longitude, not both")
        wkt_col = _require_column(columns, location_column, "--location-column")
        if input_crs is None:
            raise ValueError("CSV WKT geometry requires --input-crs")
        try:
            geometry = gpd.GeoSeries.from_wkt(table[wkt_col], crs=input_crs)
        except (TypeError, ValueError, GEOSException) as exc:
            raise ValueError("invalid WKT geometry in CSV") from exc
        return gpd.GeoDataFrame(
            table.drop(columns=[wkt_col]), geometry=geometry, crs=input_crs
        )

    if latitude_column is None or longitude_column is None:
        raise ValueError(
            "CSV requires --location-column (WKT), or both "
            "--latitude-column and --longitude-column"
        )
    if input_crs is not None and input_crs.upper() != "EPSG:4326":
        raise ValueError("CSV latitude/longitude use EPSG:4326; omit --input-crs")
    lat_col = _require_column(columns, latitude_column, "--latitude-column")
    lon_col = _require_column(columns, longitude_column, "--longitude-column")
    if lat_col == lon_col:
        raise ValueError("latitude and longitude columns must differ")
    latitude = pd.to_numeric(table[lat_col], errors="coerce")
    longitude = pd.to_numeric(table[lon_col], errors="coerce")
    if (
        latitude.isna().any()
        or longitude.isna().any()
        or not np.isfinite(latitude.to_numpy()).all()
        or not np.isfinite(longitude.to_numpy()).all()
        or (latitude.abs() > 90).any()
        or (longitude.abs() > 180).any()
    ):
        raise ValueError("CSV contains invalid WGS84 latitude/longitude")
    geometry = gpd.points_from_xy(longitude, latitude)
    return gpd.GeoDataFrame(table, geometry=geometry, crs="EPSG:4326")


def normalize_population_grid(
    input_path: str | Path,
    output_path: str | Path,
    *,
    population_column: str,
    id_column: str,
    location_column: str | None = None,
    latitude_column: str | None = None,
    longitude_column: str | None = None,
    input_crs: str | None = None,
    layer: str | None = None,
    zip_member: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Produce one GPKG layer containing ID, LOCALIZACAO, POPULACAO only."""
    input_file = Path(input_path).expanduser().resolve()
    output_file = Path(output_path).expanduser().resolve()
    if output_file.suffix.lower() != ".gpkg":
        raise ValueError("output must be a .gpkg GeoPackage file")
    if output_file == input_file:
        raise ValueError("input and output must differ")
    metadata_file = output_file.with_suffix(".metadata.json")
    if not overwrite and (output_file.exists() or metadata_file.exists()):
        raise FileExistsError(f"output already exists: {output_file}")

    source, ext, member = _source(input_file, zip_member)
    grid = _read_input(
        input_file,
        source,
        ext,
        member,
        layer=layer,
        input_crs=input_crs,
        id_column=id_column,
        population_column=population_column,
        location_column=location_column,
        latitude_column=latitude_column,
        longitude_column=longitude_column,
    )
    if grid.empty:
        raise ValueError("input grid has no features")
    if grid.crs is None:
        raise ValueError("input grid must specify a CRS")
    source_crs = str(grid.crs)
    geometry_name = grid.geometry.name
    columns = [column for column in grid.columns if column != geometry_name]
    population_name = _require_column(columns, population_column, "--population-column")
    id_name = _require_column(columns, id_column, "--id-column")
    if id_name == population_name:
        raise ValueError("ID and population columns must differ")

    if (
        grid.geometry.isna().any()
        or grid.geometry.is_empty.any()
        or not grid.geometry.is_valid.all()
    ):
        raise ValueError("some grid cells lack valid spatial geometry")
    if not grid.geometry.geom_type.isin(["Point", "Polygon", "MultiPolygon"]).all():
        raise ValueError("population locations must be points or polygons")
    populations = pd.to_numeric(grid[population_name], errors="coerce")
    if (
        populations.isna().any()
        or not np.isfinite(populations.to_numpy(dtype=float)).all()
    ):
        raise ValueError("POPULACAO must contain finite numeric values")
    if (populations < 0).any():
        raise ValueError("POPULACAO must not be negative")

    ids = grid[id_name].astype("string")
    if ids.isna().any() or ids.str.strip().eq("").any():
        raise ValueError("ID must not be null or empty")
    if ids.duplicated().any():
        raise ValueError("ID values must be unique")

    normalized = gpd.GeoDataFrame(
        {
            "ID": ids.reset_index(drop=True).astype(str),
            "POPULACAO": populations.reset_index(drop=True).astype(float),
            "LOCALIZACAO": grid.geometry.reset_index(drop=True),
        },
        geometry="LOCALIZACAO",
        crs=grid.crs,
    ).to_crs("EPSG:4326")
    bounds = normalized.total_bounds
    if (
        not np.isfinite(bounds).all()
        or bounds[0] < -180
        or bounds[2] > 180
        or bounds[1] < -90
        or bounds[3] > 90
    ):
        raise ValueError("geometry is outside WGS84 bounds; check the input CRS")
    normalized = normalized[["ID", "LOCALIZACAO", "POPULACAO"]]

    metadata = {
        "schema": "cidade15-population-v2",
        "fields": ["ID", "LOCALIZACAO", "POPULACAO"],
        "input": str(input_file),
        "output": str(output_file),
        "source_crs": source_crs,
        "output_crs": "EPSG:4326",
        "source_population_column": population_name,
        "source_id_column": id_name,
        "cells": len(normalized),
        "zero_population_cells": int((populations == 0).sum()),
        "total_population": float(populations.sum()),
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_file.parent) as tmp:
        temp_gpkg = Path(tmp) / "grid.gpkg"
        temp_metadata = Path(tmp) / "grid.metadata.json"
        normalized.to_file(
            temp_gpkg,
            layer="grade_populacional",
            driver="GPKG",
            engine="pyogrio",
            layer_options={"GEOMETRY_NAME": "LOCALIZACAO"},
        )
        temp_metadata.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_gpkg, output_file)
        os.replace(temp_metadata, metadata_file)
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fifteen-minute-city-normalize-population",
        description="Normalize population grids to ID, LOCALIZACAO, POPULACAO",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--population-column", required=True)
    parser.add_argument("--id-column", required=True)
    parser.add_argument(
        "--location-column",
        help="Spatial column in vector files (default: native geometry), or WKT in CSV",
    )
    parser.add_argument("--latitude-column")
    parser.add_argument("--longitude-column")
    parser.add_argument(
        "--input-crs", help="CRS for WKT in CSV or vector files without CRS"
    )
    parser.add_argument("--layer")
    parser.add_argument("--zip-member")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = normalize_population_grid(
            args.input,
            args.output,
            population_column=args.population_column,
            id_column=args.id_column,
            location_column=args.location_column,
            latitude_column=args.latitude_column,
            longitude_column=args.longitude_column,
            input_crs=args.input_crs,
            layer=args.layer,
            zip_member=args.zip_member,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
