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

    tree = cKDTree(node_coords)

    location_services = {}
    data_to_db = {}
    for tag, services in points.items():
        location_service = []   
        data = []
        for service, coordinate in services.items():
            pair_coordinates = np.array([
                [coordinate.x, coordinate.y]
            ])
            distances, id = tree.query(pair_coordinates, k=1)
            node_id = [node_ids[idx] for idx in id][0]
            node_data = [service,node_id,coordinate]
            location_service.append(node_id)
            data.append(node_data)
        location_services[tag] = location_service
        data_to_db[tag] = data

    print(data_to_db)
    '''
    "data_to_db" -> "servico" TABLE

    data_to_db returns:

    {
        'bank': [
            ['Bank Name', NODEID, GEOM],
            ...
        ],
        'supermarket': [
            ['Supermarket Name', NODEID, GEOM],
            ...
        ],
        ...
    }
    '''

    result = []
    
    for tag, points in location_services.items():
        time = nx.multi_source_dijkstra_path_length(G, sources=points, weight='travel_time')
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