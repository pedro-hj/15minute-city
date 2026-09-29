import argparse
from pathlib import Path

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

    return parser


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
    city.locate_services(
        ["bus_station", "school", "fuel", "bank", "hospital", "pharmacy", "supermarket"]
    )
    times = city.calculate_times(args.algorithm)
    print(times)


if __name__ == "__main__":
    main()
