import argparse

from fifteen_minute_city.core.modules.locales import Region


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--state")
    parser.add_argument("--country", default="Brazil")

    return parser


def main() -> None:

    parser = build_parser()
    args = parser.parse_args()
    locale = {"city": args.city, "country": args.country}
    if args.state:
        locale["state"] = args.state

    city = Region(locale, "walk", 3)
    city.build_graph()
    city.locate_services(
        ["bus_station", "school", "fuel", "bank", "hospital", "pharmacy", "supermarket"]
    )
    times = city.calculate_times("dijkstra")
    print(times)


if __name__ == "__main__":
    main()
