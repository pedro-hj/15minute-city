import os
import pickle
import subprocess as sp
import geopandas as gpd
import networkx as nx
import osmnx as ox
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString
from fifteen_minute_city.constants import PATH_PBF_PATH, PATH_OSM_MAPS

def load_osm_graph(pbf_filename: str, region: dict, network_type: str = "walk"):
    os.makedirs(PATH_OSM_MAPS, exist_ok=True)
    
    pbf_source_path = os.path.join(PATH_PBF_PATH, pbf_filename)
    base_region_path = os.path.join(PATH_OSM_MAPS, region['city'])
    
    pbf_raw = f"{base_region_path}.osm.pbf"
    pbf_filtered = f"{base_region_path}_{network_type}.osm.pbf"
    geojson_filtered = f"{base_region_path}_{network_type}.geojson"
    pkl_cache = f"{base_region_path}_{network_type}.pkl"

    # Loads the cache, if it exists
    if os.path.exists(pkl_cache):
        with open(pkl_cache, "rb") as f:
            return pickle.load(f)

    # If the cache does not exist, the raw .pbf file is cropped according to the region being analyzed
    region_gdf = ox.geocode_to_gdf(region)

    '''
    PERSISTENCE POINT

    "region_gdf" -> "city" TABLE

    city_data_to_db = {
        "nome": region["city"],
        "pais": region["country"],
        "geom_limite": region_gdf["geometry"]
    }
    '''

    '''
    RECOVERY POINT

    "city" TABLE -> "region_gdf"

    region_gdf = city_data_from_db["geom_limite"]
    '''

    path_polygon = PATH_OSM_MAPS / f"{region['city']}_bounds.geojson"
    region_gdf[['geometry']].to_file(path_polygon, driver="GeoJSON")

    extract_cmd = f'osmium extract -p "{path_polygon}" "{pbf_source_path}" -o "{pbf_raw}" --overwrite'
    sp.run(extract_cmd, shell=True, check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    # Converts the file of region to a pedestrian file
    if network_type == 'walk':
        filter_cmd = (
            f'osmium tags-filter "{pbf_raw}" '
            "w/highway=footway,pedestrian,steps,path,living_street,residential,service,unclassified,tertiary,secondary,primary "
            f'-o "{pbf_filtered}" --overwrite'
        )
        sp.run(filter_cmd, shell=True, check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    # Converts pedestrian file to GeoJSON
    export_cmd = f'osmium export "{pbf_filtered}" -o "{geojson_filtered}" --overwrite'
    sp.run(export_cmd, shell=True, check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    # Builds the graph with GeoPandas
    vias_gdf = gpd.read_file(geojson_filtered)

    G = create_walking_graph(vias_gdf)

    '''
    PERSISTENCE POINT

    "G" -> "no" TABLE

    nodes_gdf, _ = ox.graph_to_gdfs(G)

    gdf_nos_db = gpd.GeoDataFrame({
        'execucao_id': execucao_id_atual,
        'osm_id': nodes_gdf.index,  
        'geom': nodes_gdf.geometry, 
        'indice_geral': None,       
        'tempo_medio_geral': None   
    }, crs="EPSG:4326")
    '''

    with open(pkl_cache, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    # Removes temp files
    for temp_file in [geojson_filtered]:
        if os.path.exists(temp_file):
            os.remove(temp_file)

    return G

def load_services_geojson(G: nx.MultiDiGraph, pbf_region_path: str, services: dict[list]):

    '''
    RECOVERY POINT

    "service" TABLE -> "services_geojson"
    '''

    # Filtering services in the analyzed region
    filter_services = (
        f'osmium tags-filter "{pbf_region_path}.osm.pbf" '
        f'{"".join([f'nwr/{name}={",".join(services)} ' for name, services in services.items()])}'
        f'-o "{pbf_region_path}_services.osm.pbf" --overwrite'
    )
    sp.run(filter_services, shell=True, check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    # Exporting data from services to GeoJSON
    export = (
        f'osmium export "{pbf_region_path}_services.osm.pbf" '
        f' -o "{pbf_region_path}_services.geojson" --overwrite'
    )
    sp.run(export, shell=True, check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    # Organizing data
    services_geojson = gpd.read_file(f"{pbf_region_path}_services.geojson")

    services_geojson['service_type'] = (
    services_geojson.get('amenity', None)
    .fillna(services_geojson.get('shop', None))
    .fillna(services_geojson.get('office', None))
    .fillna(services_geojson.get('craft', None))
    .fillna(services_geojson.get('healthcare', None))
    .fillna(services_geojson.get('fire_burning', None))
    .fillna(services_geojson.get('leisure', None))
    .fillna(services_geojson.get('tourism', None))
    .fillna(services_geojson.get('historic', None))
    .fillna('others')
    )
    services_filter = [s for service in services.values() for s in service]
    services_geojson = services_geojson[services_geojson['service_type'].isin(services_filter)]

    services_geojson['geometry'] = services_geojson.geometry.representative_point()

    result = {}
    for service_type, sub_service in services_geojson.groupby('service_type'):
        result[service_type] = dict(zip(sub_service.get('name'), sub_service.get('geometry')))

    data = organizes_data(G, result)

    '''
    PERSISTENCE POINT

    "data" -> "service" TABLE

    data returns:

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

    return data

def organizes_data(G: nx.MultiDiGraph, result: dict) -> dict:
    node_ids = list(G.nodes)
    node_coords = np.array([
        (G.nodes[n]['x'], G.nodes[n]['y'])
        for n in node_ids
    ])

    tree = cKDTree(node_coords)

    location_services = {}
    data_to_db = {}
    for tag, services in result.items():
        points = []   
        data = []
        for service, coordinate in services.items():
            pair_coordinates = np.array([
                [coordinate.x, coordinate.y]
            ])
            distances, id = tree.query(pair_coordinates, k=1)
            node_id = [node_ids[idx] for idx in id][0]
            node_data = [service,node_id,coordinate]
            points.append(node_id)
            data.append(node_data)
        location_services[tag] = points
        data_to_db[tag] = data
    return location_services

def create_walking_graph(
    vias_gdf: gpd.GeoDataFrame,
    walking_speed_kmh: float = 3.0,
    coordinate_precision: int = 7,
) -> nx.MultiDiGraph:
    if vias_gdf.empty:
        raise ValueError("O GeoDataFrame de vias está vazio.")

    if vias_gdf.crs is None:
        raise ValueError("O GeoDataFrame não possui CRS definido.")

    # Divide MultiLineStrings em LineStrings individuais.
    vias = vias_gdf.explode(index_parts=False).reset_index(drop=True)

    # Mantém apenas geometrias válidas e não vazias.
    vias = vias[
        vias.geometry.notna()
        & ~vias.geometry.is_empty
        & vias.geometry.is_valid
    ].copy()

    vias = vias[
        vias.geometry.geom_type == "LineString"
    ].copy()

    if vias.empty:
        raise ValueError(
            "Nenhuma geometria LineString válida foi encontrada."
        )

    # Guarda uma versão em latitude/longitude para os atributos x e y.
    vias_wgs84 = vias.to_crs("EPSG:4326")

    # Projeta para um CRS métrico adequado à região.
    metric_crs = vias.estimate_utm_crs()

    if metric_crs is None:
        raise ValueError(
            "Não foi possível estimar automaticamente um CRS métrico."
        )

    vias_metricas = vias.to_crs(metric_crs)

    G = nx.MultiDiGraph()

    G.graph["crs"] = "EPSG:4326"
    G.graph["metric_crs"] = str(metric_crs)

    coord_to_id = {}
    next_node_id = 1

    speed_mps = walking_speed_kmh / 3.6

    def normalize_coordinate(x, y):
        return (
            round(float(x), coordinate_precision),
            round(float(y), coordinate_precision),
        )

    def get_or_create_node(lon, lat):
        nonlocal next_node_id

        coordinate = normalize_coordinate(lon, lat)

        if coordinate not in coord_to_id:
            node_id = next_node_id
            coord_to_id[coordinate] = node_id

            G.add_node(
                node_id,
                x=coordinate[0],
                y=coordinate[1],
            )

            next_node_id += 1

        return coord_to_id[coordinate]

    for index in range(len(vias_metricas)):
        geometry_metric = vias_metricas.geometry.iloc[index]
        geometry_wgs84 = vias_wgs84.geometry.iloc[index]

        metric_coords = list(geometry_metric.coords)
        geographic_coords = list(geometry_wgs84.coords)

        if len(metric_coords) < 2:
            continue

        highway = vias.iloc[index].get("highway", "pedestrian")

        # Cada par consecutivo de coordenadas vira um segmento.
        for position in range(len(metric_coords) - 1):
            metric_start = metric_coords[position]
            metric_end = metric_coords[position + 1]

            geographic_start = geographic_coords[position]
            geographic_end = geographic_coords[position + 1]

            segment_metric = LineString(
                [metric_start, metric_end]
            )

            segment_wgs84 = LineString(
                [geographic_start, geographic_end]
            )

            length_m = float(segment_metric.length)

            if length_m <= 0:
                continue

            travel_time_s = length_m / speed_mps

            u = get_or_create_node(
                geographic_start[0],
                geographic_start[1],
            )

            v = get_or_create_node(
                geographic_end[0],
                geographic_end[1],
            )

            edge_attributes = {
                "length": length_m,
                "travel_time": travel_time_s,
                "geometry": segment_wgs84,
                "highway": highway,
            }

            # Ida.
            G.add_edge(
                u,
                v,
                **edge_attributes,
            )

            # Volta.
            G.add_edge(
                v,
                u,
                **edge_attributes,
            )
    return G
