import argparse
import json
import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

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
    parser.add_argument("--network-type", default="walk", choices=["walk"])
    parser.add_argument("--speed-kmh", type=float, default=3.0)
    parser.add_argument("--algorithm", default="dijkstra", choices=["dijkstra"])
    parser.add_argument("--enable-db", action="store_true")
    parser.add_argument("--pbf", type=Path, required=True, help="Path of the PBF file")
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
        "--overwrite",
        action="store_true",
        help="Allows overwriting an output file if it exists",
    )

    return parser


def write_result(path: Path, serialized: str, *, overwrite: bool = False) -> None:
    path_file = path.expanduser().resolve()
    path_file.parent.mkdir(parents=True, exist_ok=True)
    with open(path_file, "x" if not overwrite else "w", encoding="utf-8") as file:
        file.write(serialized + "\n")


def main(argv: Sequence[str] | None = None) -> int:

    parser = build_parser()
    args = parser.parse_args(argv)
    locale = {"city": args.city, "country": args.country}
    if args.state:
        locale["state"] = args.state

    region = Region(
        locale,
        args.network_type,
        args.speed_kmh,
        args.pbf,
        enable_db=args.enable_db,
    )
    region.build_graph()
    region.locate_services(args.services)
    times = region.calculate_times(args.algorithm)
    json_data = json.dumps(times, ensure_ascii=False, indent=2)

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
