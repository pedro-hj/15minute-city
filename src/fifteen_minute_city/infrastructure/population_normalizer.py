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

    # "SEM-ID" generates sequential IDs when the source has none.
    automatic_ids = id_column == "SEM-ID"
    columns = [population_column] if automatic_ids else [id_column, population_column]

    # Read only the columns needed, even for large national grids.
    grid = gpd.read_file(source, columns=columns)
    if grid.empty:
        raise ValueError("The input grid is empty")
    if grid.crs is None:
        raise ValueError("The input grid must have a coordinate reference system (CRS)")

    for name in columns:
        if name not in grid.columns or name == grid.geometry.name:
            raise ValueError(
                f"Invalid column '{name}'. Available: {list(grid.columns)}"
            )

    ids = (
        pd.Series(range(1, len(grid) + 1), dtype="string")
        if automatic_ids
        else grid[id_column].astype("string")
    )
    if ids.isna().any() or ids.str.strip().eq("").any() or ids.duplicated().any():
        raise ValueError("IDs must be nonempty and unique")

    population = pd.to_numeric(grid[population_column], errors="raise")
    if (
        population.isna().any()
        or not np.isfinite(population.to_numpy(dtype=float)).all()
    ):
        raise ValueError("Population must contain finite numbers")
    if (population < 0).any():
        raise ValueError("Population cannot be negative")
    if grid.geometry.isna().any() or grid.geometry.is_empty.any():
        raise ValueError("Every record must have a nonempty geometry")

    normalized = gpd.GeoDataFrame(
        {
            "ID": ids.to_numpy(dtype=str),
            "POPULATION": population.to_numpy(),
            "LOCATION": grid.geometry.to_numpy(),
        },
        geometry="LOCATION",
        crs=grid.crs,
    )

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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--population-column")
    parser.add_argument(
        "--id-column",
        help='Source ID field, or "SEM-ID" to generate sequential IDs',
    )
    parser.add_argument(
        "--list-columns",
        action="store_true",
        help="Show available input columns without normalizing",
    )
    args = parser.parse_args(argv)

    if args.list_columns:
        try:
            sample = gpd.read_file(args.input, rows=1)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print("Available columns:")
        for column in sample.columns:
            print(f"  {column}")
        return 0

    for argument in ("output", "id_column", "population_column"):
        if getattr(args, argument) is None:
            parser.error(
                f"--{argument.replace('_', '-')} is required unless --list-columns is used"
            )

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
