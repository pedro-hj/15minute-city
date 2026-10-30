import argparse
import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from fifteen_minute_city.application.analysis_runner import AnalysisOutcome
from fifteen_minute_city.constants import SERVICE_CATEGORIES
from fifteen_minute_city.core.modules.locales import Region


def _slugify(text: str) -> str:
    text_normalized = unicodedata.normalize("NFKD", text)
    text_without_accent = "".join(
        char for char in text_normalized if unicodedata.category(char) != "Mn"
    ).lower()
    text_slug = re.sub(r"[^a-z0-9]+", "-", text_without_accent).strip("-")

    if not text_slug:
        return "unknown"
    return text_slug


def resolve_output_path(
    output: Path | None,
    *,
    city: str,
    state: str | None,
    country: str,
    generated_at: datetime | None = None,
) -> Path:
    root = Path("data/output")
    if output is not None:
        if output.suffix.lower() == ".json":
            return output
        root = Path(output)

    municipality_name = (
        _slugify(f"{city}, {state}")
        if state is not None and state != ""
        else _slugify(f"{city} {country}")
    )
    formatted_date = (
        generated_at.strftime("%Y%m%dT%H%M%S%z")
        if generated_at is not None
        else datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    )
    timestamp = formatted_date + ".json"
    output_path = Path.joinpath(root, municipality_name, timestamp)

    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fifteen-minute-city",
        description="Provides statistics of reachability to a city's essential services.",
    )
    parser.add_argument("--city", required=True, help="Name of the city")
    parser.add_argument("--state", help="Name of the state")
    parser.add_argument("--country", default="Brazil", help="Name of the country")
    parser.add_argument("--pbf", type=Path, required=True, help="Path to the PBF file")
    parser.add_argument(
        "--boundary",
        type=Path,
        help="Optional local boundary file; otherwise the city is geocoded",
    )
    parser.add_argument(
        "--population-grid",
        type=Path,
        required=True,
        help="Population grid, including an IBGE ZIP file",
    )
    parser.add_argument("--population-column", default="population")
    parser.add_argument("--population-id-column")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    parser.add_argument("--network-type", default="walk", choices=["walk"])
    parser.add_argument("--speed-kmh", type=float, default=3.0)
    parser.add_argument("--threshold-minutes", type=float, default=15.0)
    parser.add_argument(
        "--services",
        nargs="+",
        choices=SERVICE_CATEGORIES,
        help=(
            "Selects which service categories will be analyzed. "
            "When omitted, all categories are analyzed"
        ),
    )
    parser.add_argument(
        "--output", type=Path, help="Path where the result will be saved"
    )
    parser.add_argument(
        "--output-mode",
        choices=("simple", "detailed"),
        default="simple",
        help=(
            "Controls the JSON content: 'simple' returns only population-weighted "
            "scores; 'detailed' also returns the graph-node comparison"
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allows overwriting an output file if it exists",
    )
    parser.add_argument(
        "--enable-db",
        action="store_true",
        help="Persist the execution using DATABASE_URL",
    )
    parser.add_argument("--verbose", action="store_true")

    return parser


def write_result(path: Path, serialized: str, *, overwrite: bool = False) -> None:
    path_file = path.expanduser().resolve()
    path_file.parent.mkdir(parents=True, exist_ok=True)
    with open(path_file, "x" if not overwrite else "w", encoding="utf-8") as file:
        file.write(serialized + "\n")


def format_output(
    outcome: AnalysisOutcome,
    *,
    locale: dict[str, str],
    output_mode: str,
) -> dict[str, Any]:
    """Select the amount of analysis information exposed in the output."""
    if output_mode == "detailed":
        return outcome.to_dict()
    if output_mode != "simple":
        raise ValueError("output_mode must be 'simple' or 'detailed'")

    population_report = outcome.population_report
    if population_report is None:
        raise ValueError("simple output requires a population-weighted report")

    return {
        "location": locale,
        "category_results": {
            category: result.coverage_percentage
            for category, result in population_report.categories.items()
        },
        "overall_result": population_report.overall_coverage_percentage,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    locale = {"city": args.city, "country": args.country}
    if args.state:
        locale["state"] = args.state

    region = Region(
        locale,
        network_type=args.network_type,
        speed=args.speed_kmh,
        pbf_path=args.pbf,
        enable_db=args.enable_db,
        threshold_minutes=args.threshold_minutes,
        cache_dir=args.cache_dir,
        boundary_path=args.boundary,
    )
    region.build_graph()
    region.locate_services(args.services)
    region.load_population_grid(
        str(args.population_grid),
        population_column=args.population_column,
        id_column=args.population_id_column,
    )
    outcome = region.calculate_accessibility()
    result = format_output(outcome, locale=locale, output_mode=args.output_mode)
    json_data = json.dumps(result, ensure_ascii=False, indent=2)

    try:
        output_path = resolve_output_path(
            args.output,
            city=args.city,
            state=args.state,
            country=args.country,
            generated_at=datetime.now().astimezone(),
        )
        write_result(output_path, json_data, overwrite=args.overwrite)
    except FileExistsError:
        parser.error(
            "Já existe um arquivo no caminho escolhido; escolha outro ou use --overwrite"
        )
    print(f"Result saved at {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
