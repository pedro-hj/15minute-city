from src.fifteen_minute_city.core.modules.locales import Region

def main():
    # Example
    city = Region({'city': 'São Paulo', 'state': 'São Paulo', 'country': 'Brazil'}, "walk", 3)
    city.build_graph()
    city.locate_services(['hospital', 'school','supermarket','bank'])
    times = city.calculate_times('dijkstra')
    print(times)


if __name__ == '__main__':
    main()