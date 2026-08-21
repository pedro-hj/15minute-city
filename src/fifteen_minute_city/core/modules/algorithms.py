import networkx as nx
import pandas as pd

def multi_source_algorithm(G: nx.MultiDiGraph, points: dict[list]) -> list:
    result = []
    for tag, points in points.items():
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
        '''
        PERSISTENCE POINT

        "data" -> "alcancabilidade_no" TABLE, "indice_cidade" TABLE
        '''
        result.append(data)
    return result
