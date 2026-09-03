from fifteen_minute_city.core.modules.locales import Region


def main():
    # Example
    city = Region({'city': 'São Paulo', 'state': 'São Paulo', 'country': 'Brazil'}, "walk", 3)
    city.build_graph()
    city.locate_services(["bus_station", "school", "fuel", "bank", "hospital", "pharmacy", "supermarket"])
    times = city.calculate_times('dijkstra')
    print(times)

if __name__ == '__main__':
    main()