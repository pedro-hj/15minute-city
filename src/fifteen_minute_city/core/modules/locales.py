import osmnx as ox
import networkx as nx
import pathlib
from fifteen_minute_city.core.modules.algorithms import multi_source_algorithm
from fifteen_minute_city.core.modules.osm_utils import load_osm_graph
from fifteen_minute_city.core.modules.osm_utils import load_services_geojson
from fifteen_minute_city.constants import PATH_OSM_MAPS

ox.graph_from_address
class Region:
    __tags = {
        "amenity": ["bus_station", "school", "fuel", "bank", "hospital", "pharmacy"],
        "shop": ["supermarket"],
    }

    def __init__(self, locale: dict, network_type: str, speed: float):
        self.locale = locale
        self.network_type = network_type
        self.speed = speed
        self.__graph = None
        self.__services = {}
        self.__path = None

    def build_graph(self) -> nx.MultiDiGraph:

        hwy_speeds = {
            "motorway": self.speed,
            "trunk": self.speed,
            "primary": self.speed,
            "secondary": self.speed,
            "tertiary": self.speed,
            "residential": self.speed,
            "service": self.speed,
        }

        folder = PATH_OSM_MAPS
        folder.mkdir(exist_ok=True, parents=True)

        possible_graph = list(folder.rglob(f"{self.locale}_{self.network_type}.osm"))
        possible_graph = (
            [str(g.resolve()) for g in possible_graph][0]
            if len(possible_graph) > 0
            else ""
        )

        graph = load_osm_graph("sudeste-260714.osm.pbf",self.locale,self.network_type)
        graph = ox.add_edge_speeds(graph, hwy_speeds=hwy_speeds)
        graph = ox.add_edge_travel_times(graph)

        self.__graph = graph
        self.__path = PATH_OSM_MAPS / self.locale['city']

        print(f"Graph of region \033[1m{self.locale['city']}\033[0m successfully generated.")

        return self.__graph

    def locate_services(self, services: list) -> dict:
        
        s_formatted = {}
        for name, tag in Region.__tags.items():
            s_formatted[name] = list(set(services) & set(tag))

        self.__services = load_services_geojson(self.__graph, self.__path, s_formatted)
        return self.__services

    def calculate_times(self, algorithm: str) -> list:
        if algorithm == 'dijkstra':
            result = multi_source_algorithm(self.__graph, self.__services)
            return result
