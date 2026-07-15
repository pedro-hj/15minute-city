import osmnx as ox
import networkx as nx
import pathlib
from fifteen_minute_city.core.modules.algorithms import multi_source_algorithm
from fifteen_minute_city.core.modules.exceptions import ServiceNotSupportedError

PATH_GRAPHS = "src/fifteen_minute_city/core/outputs/graph_locales"


class Region:
    __tags = {
        "amenity": ["bus_station", "school", "fuel", "bank", "hospital", "pharmacy"],
        "shop": ["supermarket"],
    }

    def __init__(self, name: str, network_type: str, speed: float):
        self.name = name
        self.network_type = network_type
        self.speed = speed
        self.__graph = None
        self.__services = {}

    def build_graph(self, view_path: bool = False) -> nx.MultiDiGraph:
        """Method that build a graph and store it in .graphml"""

        hwy_speeds = {
            "motorway": self.speed,
            "trunk": self.speed,
            "primary": self.speed,
            "secondary": self.speed,
            "tertiary": self.speed,
            "residential": self.speed,
            "service": self.speed,
        }

        folder = pathlib.Path(PATH_GRAPHS)
        folder.mkdir(exist_ok=True, parents=True)

        possible_graph = list(folder.rglob(f"{self.name}_{self.network_type}.graphml"))
        possible_graph = (
            [str(g.resolve()) for g in possible_graph][0]
            if len(possible_graph) > 0
            else ""
        )

        graph = (
            ox.load_graphml(f"{PATH_GRAPHS}/{self.name}_{self.network_type}.graphml")
            if self.name in possible_graph
            else ox.graph_from_place(self.name, network_type=self.network_type)
        )
        graph = ox.add_edge_speeds(graph, hwy_speeds=hwy_speeds)
        graph = ox.add_edge_travel_times(graph)

        if not possible_graph:
            ox.io.save_graphml(graph, filepath=f"{PATH_GRAPHS}/{self.name}_{self.network_type}.graphml")

        path_graph = list(folder.rglob(f"{self.name}_{self.network_type}.graphml"))[0].resolve()

        self.__graph = graph

        if view_path:
            print(f"Graph of region \033[1m{self.name}\033[0m successfully generated at:\n\033[3m{path_graph}\033[0m")
        else:
            print(f"Graph of region \033[1m{self.name}\033[0m successfully generated.")

        return self.__graph

    def locate_services(self, services: list[str]) -> dict:
        """..."""
        if (
            len(
                [
                    service
                    for service in services
                    if any(service in tag for tag in Region.__tags.values()) is False
                ]
            )
            > 0
        ):
            raise ServiceNotSupportedError(
                "Some services included not are suported on this version."
            )

        tags = [
            {"amenity": service}
            if service in Region.__tags["amenity"]
            else {"shop": service}
            for service in services
        ]
        print(f"The services choosen are: \033[1m\033[3m{tags}\033[0m.")

        for tag in tags:
            places = ox.features_from_place(self.name, tag).dropna(subset=["name"])
            places = places[["name", "geometry"]]
            [name_service] = tag.values()
            self.__services[name_service] = [
                {local["name"]: ox.nearest_nodes(self.__graph, X=local.geometry.representative_point().x, Y=local.geometry.representative_point().y)}
                for id, local in places.iterrows()
            ]

        return self.__services

    def calculate_times(self, algorithm: str, chosen_services: list[str] = None) -> list:
        services = self.__services
        if chosen_services:
            services = {
                service: value
                for service, value in self.__services.items()
                if service in chosen_services
            }
        
        services_nodes = {}
        for service, points in services.items():
            nodes = []
            for point in points:
                [point_geo] = point.values()
                nodes.append(point_geo)
            services_nodes[service] = nodes

        if algorithm == 'dijkstra':
            return multi_source_algorithm(self.__graph, services_nodes)

# Example
# praia_grande = Region("Praia Grande, Sao Paulo, Brazil", "walk", 3)
# G = praia_grande.build_graph()
# services = praia_grande.locate_services(["bus_station", "bank", "school"])
# times = praia_grande.calculate_times('dijkstra', ['bank'])

# print(times)
