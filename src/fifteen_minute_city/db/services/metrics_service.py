from typing import List, Dict, Any, Optional
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from fifteen_minute_city.db.models.node import Node
from fifteen_minute_city.db.models.service import Service
from fifteen_minute_city.db.models.metrics import NodeReachability, CityIndex


def bulk_save_nodes(
    db: Session,
    execution_id: int,
    nodes_data: List[Dict[str, Any]],
) -> Dict[int, int]:
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


def bulk_save_services(
    db: Session,
    execution_id: int,
    services_data: List[Dict[str, Any]],
) -> List[Service]:
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


def bulk_save_node_reachabilities(
    db: Session,
    reachabilities_data: List[Dict[str, Any]],
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
    city_indices_data: List[Dict[str, Any]],
) -> List[CityIndex]:
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


def get_city_indices_for_execution(db: Session, execution_id: int) -> List[CityIndex]:
    """Retrieve aggregated city index metrics for a specific execution."""
    return list(
        db.scalars(
            select(CityIndex).where(CityIndex.execution_id == execution_id)
        ).all()
    )
