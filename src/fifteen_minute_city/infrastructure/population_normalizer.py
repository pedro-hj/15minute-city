import geopandas as gpd
import pandas as pd
import argparse
from pathlib import Path


def normalize(
    file,
    id_column,
    population_column,
    output,
):
    # Ler a grade original
    gdf = gpd.read_file(file)

    # Selecionar somente os campos necessários
    gdf = gdf[
        [
            id_column,
            population_column,
            gdf.geometry.name,
        ]
    ].copy()

    # Padronizar os nomes
    gdf = gdf.rename(
        columns={
            id_column: "ID",
            population_column: "POPULATION",
        }
    )

    gdf = gdf.rename_geometry("LOCATION")

    # Garantir população numérica
    gdf["POPULATION"] = pd.to_numeric(
        gdf["POPULATION"],
        errors="raise",
    )

    # Exportar formato universal
    gdf.to_file(
        output,
        driver="GPKG",
        layer="populacao",
    )

    return gdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fifteen-minute-city-normalize-population",
        description="Normalize population grids to ID, LOCATION, POPULATION",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--population-column", required=True)
    parser.add_argument("--id-column", required=True)
    args = parser.parse_args(argv)
    try:
        report = normalize(
            args.input,
            args.id_column,
            args.population_column,
            args.output
        )
        return report
    except (OSError, ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    # print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
