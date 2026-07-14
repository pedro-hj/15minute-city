import osmnx as ox
import pathlib

PATH_GRAPHS = '../outputs/graph_locales'

class Region:
    def __init__(self, name: str, network_type: str, speed: float):
        self.name = name
        self.network_type = network_type
        self.speed = speed

    def build_graph(self):

        hwy_speeds = {
            "motorway": self.speed,
            "trunk": self.speed,
            "primary": self.speed,
            "secondary": self.speed,
            "tertiary": self.speed,
            "residential": self.speed,
            "service": self.speed,
        }

        folder = pathlib.Path('../outputs')

        possible_graph = list(folder.rglob(f'{self.name}.graphml'))
        possible_graph = [str(g.resolve()) for g in possible_graph][0] if len(possible_graph) > 0 else ''
        
        graph = ox.load_graphml(f"{PATH_GRAPHS}/{self.name}.graphml") if self.name in possible_graph else ox.graph_from_place(self.name, network_type=self.network_type)
        graph = ox.add_edge_speeds(graph, hwy_speeds=hwy_speeds)
        graph = ox.add_edge_travel_times(graph)

        if not possible_graph:
            ox.io.save_graphml(
                graph, filepath=f"{PATH_GRAPHS}/{self.name}.graphml"
            )

        path_graph = list(folder.rglob(f'{self.name}.graphml'))[0].resolve()

        print(f'Graph of region \033[1m{self.name}\033[0m successfully generated at:\n\033[3m{path_graph}\033[0m')
        return graph

# Example
# praia_grande = Region('Praia Grande, Sao Paulo, Brazil', 'walk', 3)
# praia_grande.build_graph()