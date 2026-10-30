"""FMC1 exporter binary contract tests."""

import struct

import networkx as nx
import pytest

from fifteen_minute_city.application.simulation_package import (
    HEADER,
    MAGIC,
    build_package,
)


def sample_graph():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    for identifier, lon in ((11, 0), (22, 0.005), (33, 0.01)):
        graph.add_node(identifier, x=lon, y=0.0)
    graph.add_edge(11, 22, length=1_000)
    graph.add_edge(22, 33, length=1_000)
    return graph


def sample_kwargs():
    return {
        "execution_id": 7,
        "speed_kmh": 3.0,
        "threshold_minutes": 15.0,
        "categories": ["health", "food"],
        "population_by_osm": {11: 50, 22: 0, 33: 50},
        "baseline_minutes": {
            (11, "health"): 0.0,
            (11, "food"): 40.0,
            (22, "health"): 20.0,
            (22, "food"): 20.0,
            (33, "health"): 40.0,
            (33, "food"): 0.0,
        },
        "pbf_checksum": "a" * 64,
        "graph_cache_key": "b" * 24,
    }


def test_binary_package_preserves_reverse_edge_orientation():
    bundle = build_package(sample_graph(), **sample_kwargs())
    magic, metadata_len, nodes, edges, categories = HEADER.unpack_from(bundle)
    assert magic == MAGIC
    assert (nodes, edges, categories) == (3, 2, 2)
    data_offset = (HEADER.size + metadata_len + 7) // 8 * 8
    offset_location = data_offset + 8 * (3 * nodes + nodes * categories)
    offsets = struct.unpack_from("<4I", bundle, offset_location)
    assert offsets == (0, 0, 1, 2)

    neighbors_location = offset_location + 4 * (nodes + 1)
    assert struct.unpack_from("<2I", bundle, neighbors_location) == (0, 1)
    times_location = neighbors_location + 4 * edges
    assert struct.unpack_from("<2d", bundle, times_location) == (1200.0, 1200.0)


def test_binary_export_rejects_missing_population_nodes():
    parameters = sample_kwargs()
    parameters["population_by_osm"] = {11: 50, 33: 50}
    with pytest.raises(ValueError, match="exactly"):
        build_package(sample_graph(), **parameters)


def test_binary_export_rejects_missing_baseline_records():
    parameters = sample_kwargs()
    parameters["baseline_minutes"].pop((11, "food"))
    with pytest.raises(ValueError, match="Missing baseline"):
        build_package(sample_graph(), **parameters)
