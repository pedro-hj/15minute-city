import osmnx as ox
import networkx as nx
import typer

app = typer.Typer()


def get_locations(tags: list[dict], place: str) -> dict:

    locations = {}

    for tag in tags:
        services_locations = []
        places = ox.features_from_place(place, tag)

        for idx, local in places.iterrows():
            geom = local.geometry

            if not hasattr(geom, "x"):
                geom = geom.centroid

            lat = geom.y
            lon = geom.x

            services_locations.append(
                {local["name"]: ox.distance.nearest_nodes(G, X=lon, Y=lat)}
            )

        locations[tag["amenity"]] = services_locations

    return locations


def get_times(services_location: dict[dict]) -> dict:

    result = {}

    for type_service, services in services_location.items():
        times = []
        for service in services:
            for name_service, location_service in service.items():
                path_time, paths = nx.single_source_dijkstra(
                    G, location_service, weight="travel_time"
                )
                times.append(
                    {name_service: (sum(path_time.values()) / len(path_time)) / 60}
                )
        result[type_service] = times

    return result


def get_averages(times: dict) -> list:
    general_average = []
    average_total = 0
    cont = 0
    for type_service, services in times.items():
        average_service = 0
        for service in services:
            ((name, avg),) = service.items()
            average_service += avg
            cont += 1
        average_total += average_service
        general_average.append({type_service: average_service / len(services)})
    general_average.append({"general_average": average_total / cont})

    return general_average


@app.command()
def run(place: str, net_type: str, hwy_speed: int):

    typer.echo(
        f"Local: {place}\nTipo de transporte: {net_type}\nVelocidade: {hwy_speed} km/h"
    )
    typer.echo("-" * 50)
    global G
    G = ox.graph_from_place(place, network_type=net_type)

    tags = [
        {"amenity": "bus_station"},
        {"amenity": "school"},
        {"amenity": "fuel"},
        {"amenity": "bank"},
        {"amenity": "hospital"},
        {"amenity": "pharmacy"},
        {"shop": "supermarket"},
    ]

    hwy_speeds = {
        "motorway": hwy_speed,
        "trunk": hwy_speed,
        "primary": hwy_speed,
        "secondary": hwy_speed,
        "tertiary": hwy_speed,
        "residential": hwy_speed,
        "service": hwy_speed,
    }

    G = ox.add_edge_speeds(G, hwy_speeds=hwy_speeds)
    G = ox.add_edge_travel_times(G)

    results = get_times(get_locations(tags, place))

    general_average = get_averages(results)
    return typer.echo(general_average)


if __name__ == "__main__":
    app()
