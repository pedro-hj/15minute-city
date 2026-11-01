"""Normalize population grids from different statistical agencies into GeoPackage.

The output preserves source geometries while standardizing the population, cell
identifier, provenance, and imputation indicator consumed by the City15 CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PopulationProfile:
    country: str | None
    source: str
    population_column: str | None
    id_column: str | None
    estimated_column: str | None = None
    year: int | None = None


PROFILES = {
    "ibge": PopulationProfile("Brazil", "IBGE", "TOTAL", "ID_UNICO"),
    "insee-filosofi-2021": PopulationProfile(
        "France", "INSEE Filosofi", "ind", "idcar_200m", "i_est_200", 2021
    ),
    "custom": PopulationProfile(None, "custom", None, None),
}

_VECTOR_EXTENSIONS = {".gpkg", ".shp", ".geojson", ".json"}


def _vector_source(path: Path, zip_member: str | None) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"population grid not found: {path}")
    if path.suffix.lower() != ".zip":
        if zip_member is not None:
            raise ValueError("--zip-member requires a ZIP input")
        if path.suffix.lower() not in _VECTOR_EXTENSIONS:
            raise ValueError("unsupported population file; use GPKG, SHP, GeoJSON or ZIP")
        return str(path)

    with ZipFile(path) as archive:
        members = [
            name
            for name in archive.namelist()
            if not name.endswith("/") and Path(name).suffix.lower() in _VECTOR_EXTENSIONS
        ]
    if zip_member is not None:
        if zip_member not in members:
            raise ValueError(f"ZIP does not contain geospatial member '{zip_member}'")
        chosen = zip_member
    else:
        # A shapefile archive also contains .dbf/.shx/.prj sidecars; only its
        # .shp member counts as an independent spatial dataset.
        if len(members) != 1:
            raise ValueError(
                "ZIP must contain exactly one vector dataset; "
                "select one with --zip-member"
            )
        chosen = members[0]
    return f"zip://{path}!{chosen}"


def _read_grid(
    source: str, *, boundary_path: Path | None, layer: str | None
) -> tuple[gpd.GeoDataFrame, str]:
    options = {"layer": layer} if layer else {}
    sample = gpd.read_file(source, rows=1, **options)
    if sample.crs is None:
        raise ValueError("population grid must define a CRS")
    source_crs = str(sample.crs)
    if boundary_path is None:
        return gpd.read_file(source, **options), source_crs

    boundary = gpd.read_file(boundary_path)
    if boundary.empty or boundary.crs is None:
        raise ValueError("boundary must not be empty and must define a CRS")
    projected_boundary = boundary.to_crs(sample.crs)
    candidates = gpd.read_file(
        source, bbox=tuple(projected_boundary.total_bounds), **options
    )
    if candidates.empty:
        raise ValueError("population grid does not intersect the requested boundary")
    valid = candidates.geometry.notna() & ~candidates.geometry.is_empty
    candidates = candidates.loc[valid].copy()
    area = projected_boundary.geometry.union_all()
    representative_points = candidates.geometry.representative_point()
    result = candidates.loc[representative_points.covered_by(area)].copy()
    if result.empty:
        raise ValueError("no population cell centers fall inside the boundary")
    return result, source_crs


def normalize_population_grid(
    input_path: str | Path,
    output_path: str | Path,
    *,
    profile: str = "custom",
    country: str | None = None,
    source_name: str | None = None,
    year: int | None = None,
    population_column: str | None = None,
    id_column: str | None = None,
    estimated_column: str | None = None,
    boundary: str | Path | None = None,
    layer: str | None = None,
    zip_member: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Write a standard spatial grid and a provenance/quality metadata sidecar."""
    if profile not in PROFILES:
        raise ValueError(f"unknown population profile '{profile}'")
    defaults = PROFILES[profile]
    country = country or defaults.country
    source_name = source_name or defaults.source
    population_column = population_column or defaults.population_column
    id_column = id_column or defaults.id_column
    estimated_column = estimated_column or defaults.estimated_column
    year = year if year is not None else defaults.year
    if not country or not population_column or not id_column:
        raise ValueError("country, population column and ID column are required")
    if year is not None and year <= 0:
        raise ValueError("year must be positive")

    input_file = Path(input_path).expanduser().resolve()
    output_file = Path(output_path).expanduser().resolve()
    if output_file.suffix.lower() != ".gpkg":
        raise ValueError("normalized output must be a .gpkg file")
    if input_file == output_file:
        raise ValueError("input and output paths must differ")
    metadata_file = output_file.with_suffix(".metadata.json")
    if not overwrite and (output_file.exists() or metadata_file.exists()):
        raise FileExistsError(f"normalized output already exists: {output_file}")

    boundary_file = Path(boundary).expanduser().resolve() if boundary else None
    source = _vector_source(input_file, zip_member)
    grid, source_crs = _read_grid(source, boundary_path=boundary_file, layer=layer)
    if grid.empty:
        raise ValueError("population grid must contain at least one feature")
    required_columns = {population_column, id_column}
    if estimated_column:
        required_columns.add(estimated_column)
    missing = required_columns.difference(grid.columns)
    if missing:
        raise ValueError(f"population grid is missing columns: {', '.join(sorted(missing))}")

    valid = grid.geometry.notna() & ~grid.geometry.is_empty
    grid = grid.loc[valid].copy()
    values = pd.to_numeric(grid[population_column], errors="coerce")
    if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("population values must be finite and numeric")
    if (values < 0).any():
        raise ValueError("population values must not be negative")
    identifiers = grid[id_column].astype("string")
    if identifiers.isna().any() or (identifiers.str.strip() == "").any():
        raise ValueError("grid identifiers must not be empty")
    if identifiers.duplicated().any():
        raise ValueError("grid identifiers must be unique")

    estimate = pd.Series(pd.NA, index=grid.index, dtype="Int64")
    if estimated_column:
        raw = grid[estimated_column]
        numeric = pd.to_numeric(raw, errors="coerce")
        nonempty = raw.notna()
        if (nonempty & (~numeric.isin([0, 1]))).any():
            raise ValueError("estimated flag must contain only 0, 1 or null")
        estimate = numeric.astype("Int64")

    positive = values > 0
    removed_zero_cells = int((~positive).sum())
    grid = grid.loc[positive].copy()
    identifiers = identifiers.loc[positive]
    values = values.loc[positive]
    estimate = estimate.loc[positive]
    if grid.empty:
        raise ValueError("population grid has no cells with positive population")
    # Make positional arrays and geometry align even after bbox filtering.
    grid = grid.reset_index(drop=True)
    identifiers = identifiers.reset_index(drop=True)
    values = values.reset_index(drop=True)
    estimate = estimate.reset_index(drop=True)

    # Use source-CRS interior points before reprojecting the geometry; this
    # matters for large or curved geographic cells.
    points = grid.geometry.representative_point().to_crs("EPSG:4326")
    normalized = gpd.GeoDataFrame(
        {
            "grid_id": identifiers.to_numpy(dtype=str),
            "population": values.to_numpy(dtype=float),
            "country": country,
            "source": source_name,
            "source_year": year,
            "estimated": estimate.to_numpy(dtype="float64", na_value=np.nan),
            "longitude": points.x.to_numpy(),
            "latitude": points.y.to_numpy(),
            "geometry": grid.geometry,
        },
        crs=grid.crs,
    ).to_crs("EPSG:4326")
    # GPKG supports nullable integer fields. Avoid NaN-to-boolean ambiguity.
    normalized["estimated"] = pd.Series(
        pd.array(estimate.to_numpy(), dtype="Int64"), index=normalized.index
    )

    known = estimate.notna()
    imputed = estimate == 1
    metadata = {
        "schema": "cidade15-population-v1",
        "country": country,
        "source": source_name,
        "source_year": year,
        "input": str(input_file),
        "output": str(output_file),
        "boundary": str(boundary_file) if boundary_file else None,
        "source_crs": source_crs,
        "output_crs": "EPSG:4326",
        "population_column": population_column,
        "id_column": id_column,
        "estimated_column": estimated_column,
        "cells": len(normalized),
        "zero_population_cells_removed": removed_zero_cells,
        "total_population": float(values.sum()),
        "estimated_cells": int(imputed.sum()),
        "estimated_population": float(values.loc[imputed.fillna(False)].sum()),
        "unknown_estimation_cells": int((~known).sum()),
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_file.parent) as temp_dir:
        temp_gpkg = Path(temp_dir) / "population.gpkg"
        temp_metadata = Path(temp_dir) / "population.metadata.json"
        normalized.to_file(temp_gpkg, layer="population_grid", driver="GPKG")
        temp_metadata.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temp_gpkg, output_file)
        os.replace(temp_metadata, metadata_file)
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fifteen-minute-city-normalize-population",
        description="Normalize international population grids to Cidade15 GeoPackage",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=tuple(PROFILES), required=True)
    parser.add_argument("--country")
    parser.add_argument("--source-name")
    parser.add_argument("--year", type=int)
    parser.add_argument("--population-column")
    parser.add_argument("--id-column")
    parser.add_argument("--estimated-column")
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--layer")
    parser.add_argument("--zip-member", help="Path to the spatial dataset inside a ZIP")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        metadata = normalize_population_grid(
            args.input,
            args.output,
            profile=args.profile,
            country=args.country,
            source_name=args.source_name,
            year=args.year,
            population_column=args.population_column,
            id_column=args.id_column,
            estimated_column=args.estimated_column,
            boundary=args.boundary,
            layer=args.layer,
            zip_member=args.zip_member,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
