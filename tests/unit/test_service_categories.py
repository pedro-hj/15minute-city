import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

from fifteen_minute_city.constants import SERVICE_CATEGORIES
from fifteen_minute_city.infrastructure.osm.services import (
    categorize_services,
    snap_services_to_graph,
)


def test_expected_categories() -> None:
    assert SERVICE_CATEGORIES == {
        "health": [
            ("amenity", "hospital"),
            ("amenity", "clinic"),
            ("amenity", "doctors"),
            ("amenity", "pharmacy"),
            ("healthcare", "hospital"),
            ("healthcare", "clinic"),
        ],
        "education": [
            ("amenity", "kindergarten"),
            ("amenity", "school"),
        ],
        "food": [
            ("shop", "supermarket"),
            ("shop", "convenience"),
            ("shop", "bakery"),
            ("shop", "greengrocer"),
            ("shop", "butcher"),
            ("shop", "seafood"),
            ("shop", "deli"),
            ("amenity", "marketplace"),
        ],
        "culture": [
            ("amenity", "library"),
            ("amenity", "cinema"),
            ("tourism", "museum"),
        ],
    }


def test_osm_services_are_grouped_by_category_without_losing_duplicate_names():
    services = gpd.GeoDataFrame(
        {
            "name": ["Central", "Central", "Neighborhood", "Museum"],
            "amenity": ["hospital", "pharmacy", "school", None],
            "healthcare": [None, None, None, None],
            "shop": [None, None, None, None],
            "tourism": [None, None, None, "museum"],
            "geometry": [
                Point(0, 0),
                Point(1, 0),
                Point(2, 0),
                Point(3, 0),
            ],
        },
        crs="EPSG:4326",
    )

    categorized = categorize_services(services, SERVICE_CATEGORIES)

    assert [name for name, _point in categorized["health"]] == [
        "Central",
        "Central",
    ]
    assert [name for name, _point in categorized["education"]] == ["Neighborhood"]
    assert categorized["food"] == []
    assert [name for name, _point in categorized["culture"]] == ["Museum"]


def test_categorized_services_are_associated_with_graph_nodes_by_category():
    graph = nx.MultiDiGraph()
    graph.add_node(10, x=0.0, y=0.0)
    graph.add_node(20, x=2.0, y=0.0)
    services = {
        "health": [("Hospital", Point(0.1, 0.0))],
        "education": [("School", Point(1.9, 0.0))],
    }

    result = snap_services_to_graph(graph, services)

    assert result.nodes_by_category == {"health": [10], "education": [20]}
    assert result.organizer_data()["health"][0][:2] == ["Hospital", 10]
    assert result.organizer_data()["education"][0][:2] == ["School", 20]
