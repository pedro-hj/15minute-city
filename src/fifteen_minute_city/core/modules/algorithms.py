import networkx as nx
import pandas as pd

def multi_source_algorithm(G, points: dict[list]):
    result = []
    for name, point in points.items():
        time, path = nx.multi_source_dijkstra(G, sources=point, weight='travel_time')
        serie_times = pd.Series(time)
        data = {
            'service': name,
            'qtd_nodes': int(serie_times.count()),
            'mean': float(serie_times.mean())/60,
            'median': float(serie_times.median())/60,
            'max': float(serie_times.max())/60,
            'std': float(serie_times.std())/60
        }
        result.append(data)
    return result