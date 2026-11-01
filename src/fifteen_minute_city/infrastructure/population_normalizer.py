"""Normalize a vector population grid to ID, LOCATION and POPULATION."""

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


def normalize(file, id_column, population_column, output):
    """Copy the chosen ID, geometry and population into a GeoPackage."""
    source = Path(file)
    destination = Path(output)
    if source.resolve() == destination.resolve():
        raise ValueError("Input and output must be different files")
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination}")
    if id_column == population_column:
        raise ValueError("ID and population must use different columns")

    # A large national grid may have many unrelated statistical columns.
    grid = gpd.read_file(source, columns=[id_column, population_column])
    if grid.empty:
        raise ValueError("The input grid is empty")
    if grid.crs is None:
        raise ValueError(
            "The input grid must have a coordinate reference system (CRS)"
        )

    for name in (id_column, population_column):
        if name not in grid.columns or name == grid.geometry.name:
            raise ValueError(
                f"Invalid column '{name}'. Available: {list(grid.columns)}"
            )

    ids = grid[id_column].astype("string")
    if ids.isna().any() or ids.str.strip().eq("").any() or ids.duplicated().any():
        raise ValueError("IDs must be nonempty and unique")

    population = pd.to_numeric(grid[population_column], errors="raise")
    if population.isna().any() or not np.isfinite(
        population.to_numpy(dtype=float)
    ).all():
        raise ValueError("Population must contain finite numbers")
    if (population < 0).any():
        raise ValueError("Population cannot be negative")
    if grid.geometry.isna().any() or grid.geometry.is_empty.any():
        raise ValueError("Every record must have a nonempty geometry")

    normalized = grid[[id_column, population_column, grid.geometry.name]].copy()
    normalized = normalized.rename(
        columns={id_column: "ID", population_column: "POPULATION"}
    ).rename_geometry("LOCATION")
    normalized["ID"] = ids
    normalized["POPULATION"] = population

    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_file(
        destination,
        driver="GPKG",
        layer="population",
        engine="pyogrio",
        layer_options={"GEOMETRY_NAME": "LOCATION"},
    )
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fifteen-minute-city-normalize-population",
        description="Normalize a population grid to ID, LOCATION, POPULATION",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--population-column", required=True)
    parser.add_argument("--id-column", required=True)
    args = parser.parse_args(argv)
    try:
        result = normalize(
            args.input, args.id_column, args.population_column, args.output
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Normalized {len(result)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
