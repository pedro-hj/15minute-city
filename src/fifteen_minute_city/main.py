import argparse
import json
from pathlib import Path

from fifteen_minute_city.constants import SUPPORTED_SERVICES
from fifteen_minute_city.core.modules.locales import Region


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--state")
    parser.add_argument("--country", default="Brazil")
    parser.add_argument("--network-type", default="walk", choices=["walk"])
    parser.add_argument("--speed-kmh", type=float, default=3.0)
    parser.add_argument("--algorithm", default="dijkstra", choices=["dijkstra"])
    parser.add_argument("--enable-db", action="store_true")
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--services", nargs="+", choices=SUPPORTED_SERVICES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true")

    return parser


def write_result(path: Path, serialized: str, *, overwrite: bool = False) -> None:
    path_file = path.expanduser().resolve()
    path_file.parent.mkdir(parents=True, exist_ok=True)
    with open(path_file, "x" if not overwrite else "w", encoding="utf-8") as file:
        file.write(serialized + "\n")


def main() -> None:

    parser = build_parser()
    args = parser.parse_args()
    locale = {"city": args.city, "country": args.country}
    if args.state:
        locale["state"] = args.state

    city = Region(
        locale,
        args.network_type,
        args.speed_kmh,
        args.pbf,
        enable_db=args.enable_db,
    )
    city.build_graph()
    city.locate_services(args.services)
    times = city.calculate_times(args.algorithm)
    json_data = json.dumps(times, ensure_ascii=False, indent=2)
    if args.output is None:
        print(json_data)
    else:
        try:
            write_result(args.output, json_data, overwrite=args.overwrite)
        except FileExistsError:
            parser.error(
                "Já existe um arquivo no caminho escolhido; escolha outro ou use --overwrite"
            )


if __name__ == "__main__":
    main()
