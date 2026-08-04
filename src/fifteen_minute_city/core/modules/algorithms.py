import networkx as nx
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

def multi_source_algorithm(G, points: dict[dict]):
    node_ids = list(G.nodes)
    node_coords = np.array([
        (G.nodes[n]['x'], G.nodes[n]['y'])
        for n in node_ids
    ])
    print(len(node_coords))

    tree = cKDTree(node_coords)

    location_services = {}
    for tag, services in points.items():
        location_service = []   
        for service, coordinate in services.items():
            pair_coordinates = np.array([
                [coordinate.x, coordinate.y]
            ])
            distances, id = tree.query(pair_coordinates, k=1)
            location_service.append([node_ids[idx] for idx in id][0])
        location_services[tag] = location_service

    result = []
    
    for tag, points in location_services.items():
        print(len(G))
        print(len(points))
        time = nx.multi_source_dijkstra_path_length(G, sources=points, weight='travel_time')
        print(len(time))
        serie_times = pd.Series(time)
        data = {
            'service': tag,
            'qtd_nodes': int(serie_times.count()),
            'mean': float(serie_times.mean())/60,
            'median': float(serie_times.median())/60,
            'max': float(serie_times.max())/60,
            'std': float(serie_times.std())/60
        }
        result.append(data)
    return result