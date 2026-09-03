from typing import Any

import networkx as nx
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fifteen_minute_city.db.models.metrics import CityIndex, NodeReachability
from fifteen_minute_city.db.models.node import Node
from fifteen_minute_city.db.models.service import Service


def bulk_save_nodes(
    db: Session,
    execution_id: int,
    nodes_data: list[dict[str, Any]],
) -> dict[int, int]:
    """
    Bulk insert network nodes for an execution run.

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param nodes_data: List of dicts containing keys: 'osm_id', 'lat', 'lon', optional 'overall_index', 'overall_mean_time'.
    :return: Dictionary mapping osm_id -> database node primary key ID.
    """
    node_objects = []
    for data in nodes_data:
        geom = from_shape(Point(data["lon"], data["lat"]), srid=4326)
        node = Node(
            execution_id=execution_id,
            osm_id=data["osm_id"],
            geom=geom,
            overall_index=data.get("overall_index"),
            overall_mean_time=data.get("overall_mean_time"),
        )
        node_objects.append(node)

    db.add_all(node_objects)
    db.flush()

    # Build mapping from osm_id -> db primary key ID
    return {n.osm_id: n.id for n in node_objects}


def save_graph_nodes_from_nx(
    db: Session,
    execution_id: int,
    G: nx.MultiDiGraph,
) -> dict[int, int]:
    """
    Extract nodes from a NetworkX MultiDiGraph and bulk save them for the execution.

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param G: NetworkX MultiDiGraph with 'x' (lon) and 'y' (lat) node attributes.
    :return: Dictionary mapping osm_id -> database node primary key ID.
    """
    nodes_data = []
    for node_id, data in G.nodes(data=True):
        lon = data.get("x")
        lat = data.get("y")
        if lon is not None and lat is not None:
            nodes_data.append(
                {
                    "osm_id": int(node_id),
                    "lon": float(lon),
                    "lat": float(lat),
                }
            )

    return bulk_save_nodes(db, execution_id, nodes_data)


def bulk_save_services(
    db: Session,
    execution_id: int,
    services_data: list[dict[str, Any]],
) -> list[Service]:
    """
    Bulk insert physical service establishments for an execution run.

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param services_data: List of dicts containing: 'category_id', 'name', 'lat', 'lon', optional 'representative_node_id'.
    :return: List of created Service model instances.
    """
    service_objects = []
    for data in services_data:
        geom = from_shape(Point(data["lon"], data["lat"]), srid=4326)
        service = Service(
            execution_id=execution_id,
            category_id=data["category_id"],
            representative_node_id=data.get("representative_node_id"),
            name=data.get("name"),
            geom=geom,
        )
        service_objects.append(service)

    db.add_all(service_objects)
    db.flush()
    return service_objects


def save_services_from_organizer_dict(
    db: Session,
    execution_id: int,
    organized_data: dict[str, list[list[Any]]],
    category_id_map: dict[str, int],
    osm_to_db_node_map: dict[int, int] | None = None,
) -> list[Service]:
    """
    Save services from the organizer structure:
    {
        'category_code': [
            ['Service Name', OSM_NODE_ID, ShapelyPoint],
            ...
        ]
    }

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param organized_data: Dictionary structured from organizes_data().
    :param category_id_map: Mapping from category_code (e.g. 'bank') -> category_id.
    :param osm_to_db_node_map: Optional mapping from osm_id -> db node.id.
    :return: List of created Service model instances.
    """
    services_data = []
    for category_code, items in organized_data.items():
        cat_id = category_id_map.get(category_code)
        if not cat_id:
            continue

        for item in items:
            name = item[0] if len(item) > 0 and item[0] else category_code
            osm_node_id = item[1] if len(item) > 1 else None
            point_geom = item[2] if len(item) > 2 else None

            rep_node_id = None
            if osm_node_id is not None and osm_to_db_node_map:
                rep_node_id = osm_to_db_node_map.get(int(osm_node_id))

            if point_geom is not None and hasattr(point_geom, "x") and hasattr(point_geom, "y"):
                services_data.append(
                    {
                        "category_id": cat_id,
                        "name": str(name),
                        "lat": float(point_geom.y),
                        "lon": float(point_geom.x),
                        "representative_node_id": rep_node_id,
                    }
                )

    if services_data:
        return bulk_save_services(db, execution_id, services_data)
    return []


def get_services_by_execution(db: Session, execution_id: int) -> list[Service]:
    """Retrieve all physical services associated with a specific execution."""
    return list(
        db.scalars(
            select(Service).where(Service.execution_id == execution_id)
        ).all()
    )


def bulk_save_node_reachabilities(
    db: Session,
    reachabilities_data: list[dict[str, Any]],
) -> None:
    """
    Bulk insert travel reachability records for nodes.

    :param db: SQLAlchemy Session.
    :param reachabilities_data: List of dicts containing: 'node_id', 'category_id', 'travel_time_minutes', 'within_threshold', optional 'closest_service_id'.
    """
    reachability_objects = [
        NodeReachability(
            node_id=data["node_id"],
            category_id=data["category_id"],
            closest_service_id=data.get("closest_service_id"),
            travel_time_minutes=data["travel_time_minutes"],
            within_threshold=data["within_threshold"],
        )
        for data in reachabilities_data
    ]
    db.add_all(reachability_objects)
    db.flush()


def save_city_indices(
    db: Session,
    execution_id: int,
    city_indices_data: list[dict[str, Any]],
) -> list[CityIndex]:
    """
    Save aggregated city accessibility indices for an execution run.

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param city_indices_data: List of dicts containing: 'category_id', 'mean_travel_time_minutes', 'percentage_within_threshold', 'overall_index'.
    :return: List of created CityIndex instances.
    """
    index_objects = [
        CityIndex(
            execution_id=execution_id,
            category_id=data["category_id"],
            mean_travel_time_minutes=data["mean_travel_time_minutes"],
            percentage_within_threshold=data["percentage_within_threshold"],
            overall_index=data["overall_index"],
        )
        for data in city_indices_data
    ]
    db.add_all(index_objects)
    db.flush()
    return index_objects


def save_city_indices_from_metrics(
    db: Session,
    execution_id: int,
    metrics_list: list[dict[str, Any]],
    category_id_map: dict[str, int],
) -> list[CityIndex]:
    """
    Save city index records from the output of multi_source_algorithm():
    [
        {'service': 'bank', 'mean': 12.5, 'median': 10.2, 'std': 3.1, 'max': 25.0, 'qtd_nodes': 1000},
        ...
    ]

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param metrics_list: List of metric dictionaries.
    :param category_id_map: Mapping from service tag/code -> category_id.
    :return: List of created CityIndex instances.
    """
    city_indices_data = []
    for item in metrics_list:
        service_code = item.get("service")
        cat_id = category_id_map.get(service_code)
        if not cat_id:
            continue

        mean_time = float(item.get("mean", 0.0))
        median_time = float(item.get("median", mean_time))
        # Overall index reference based on median/threshold
        overall_index = float(median_time)
        percentage_within_threshold = float(item.get("percentage_within_threshold", 0.0))

        city_indices_data.append(
            {
                "category_id": cat_id,
                "mean_travel_time_minutes": mean_time,
                "percentage_within_threshold": percentage_within_threshold,
                "overall_index": overall_index,
            }
        )

    if city_indices_data:
        return save_city_indices(db, execution_id, city_indices_data)
    return []


def get_city_indices_for_execution(db: Session, execution_id: int) -> list[CityIndex]:
    """Retrieve aggregated city index metrics for a specific execution."""
    return list(
        db.scalars(
            select(CityIndex).where(CityIndex.execution_id == execution_id)
        ).all()
    )
