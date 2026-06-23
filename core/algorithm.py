import osmnx as ox
import networkx as nx

PLACE = "Praia Grande, São Paulo, Brazil"

G = ox.graph_from_place(PLACE, network_type="walk")

tags = [
    {"amenity": "bus_station"},
    {"amenity": "school"},
    {"amenity": "fuel"},
    {"amenity": "bank"},
    {"amenity": "hospital"},
    {"amenity": "pharmacy"},
    {"shop": "supermarket"}
]

hwy_speeds = {
    'motorway': 3,
    'trunk': 3,
    'primary': 3,
    'secondary': 3,
    'tertiary': 3,
    'residential': 3,
    'service': 3
}

G = ox.add_edge_speeds(G, hwy_speeds=hwy_speeds)
G = ox.add_edge_travel_times(G)

def get_locations(tags: list) -> list:

    services_locations = []

    for tag in tags:

        places = ox.features_from_place(PLACE, tag)

        locations = {}

        for idx, place in places.iterrows():
            geom = place.geometry

            if not hasattr(geom, "x"):
                geom = geom.centroid

            lat = geom.y
            lon = geom.x

            locations[place["name"]] = ox.distance.nearest_nodes(G, X=lon, Y=lat)

        services_locations.append(locations)

    return services_locations

l = get_locations(tags)

def get_times(services_location: list) -> dict:

    times = {}

    for service in services_location:
        for name_service, location_service in service.items():
            path_time, paths = nx.single_source_dijkstra(G, location_service, weight="travel_time")
            times[name_service] = (sum(path_time.values()) / len(path_time)) / 60
    times['general_average'] = sum(times.values()) / len(times)
    return times

l = get_locations(tags)
t = get_times(l)
print(t)