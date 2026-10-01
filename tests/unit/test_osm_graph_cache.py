from pathlib import Path

import geopandas as gpd
import networkx as nx
from shapely.geometry import box

from fifteen_minute_city.infrastructure.osm import graph as graph_module
from fifteen_minute_city.infrastructure.osm.graph import (
    _boundary_digest,
    _remove_non_walkable_edges,
    sha256_file,
)


def test_explicit_pedestrian_restrictions_are_removed() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, access="private")
    graph.add_edge(2, 3, foot="no")
    graph.add_edge(3, 4, access="private", foot="yes")

    _remove_non_walkable_edges(graph)

    assert list(graph.edges()) == [(3, 4)]
    assert set(graph.nodes) == {3, 4}


def test_sha256_file_identifies_equal_and_different_contents(tmp_path: Path) -> None:
    first = tmp_path / "first.osm.pbf"
    second = tmp_path / "second.osm.pbf"
    third = tmp_path / "third.osm.pbf"
    first.write_bytes(b"same PBF content")
    second.write_bytes(b"same PBF content")
    third.write_bytes(b"different PBF content")

    assert sha256_file(first) == sha256_file(second)
    assert sha256_file(first) != sha256_file(third)


def test_boundary_digest_identifies_equal_and_different_boundaries() -> None:
    first = gpd.GeoDataFrame(
        {"geometry": [box(-46.1, -24.1, -45.9, -23.9)]},
        crs="EPSG:4326",
    )
    equal = first.copy()
    different = gpd.GeoDataFrame(
        {"geometry": [box(-46.2, -24.2, -45.8, -23.8)]},
        crs="EPSG:4326",
    )

    assert _boundary_digest(first) == _boundary_digest(equal)
    assert _boundary_digest(first) != _boundary_digest(different)


def test_graph_cache_preserves_osm_node_ids_and_is_invalidated_by_pbf(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.osm.pbf"
    source.write_bytes(b"first-snapshot")
    boundary = gpd.GeoDataFrame(
        {"geometry": [box(-46.1, -24.1, -45.9, -23.9)]},
        crs="EPSG:4326",
    )
    command_calls = []

    def fake_osmium(arguments: list[str]) -> None:
        command_calls.append(arguments)
        output_path = Path(arguments[arguments.index("-o") + 1])
        if arguments[0] == "cat":
            output_path.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="101" lat="-24.0" lon="-46.0" />
  <node id="102" lat="-24.0" lon="-45.999" />
  <way id="501">
    <nd ref="101" />
    <nd ref="102" />
    <tag k="highway" v="residential" />
  </way>
</osm>
""",
                encoding="utf-8",
            )
        else:
            output_path.write_bytes(b"test-pbf")

    monkeypatch.setattr(graph_module, "_run_osmium", fake_osmium)

    first = graph_module.load_or_build_osm_graph(source, boundary, tmp_path / "cache")
    first_call_count = len(command_calls)
    second = graph_module.load_or_build_osm_graph(source, boundary, tmp_path / "cache")

    assert first.cache_hit is False
    assert set(first.graph.nodes) == {101, 102}
    assert second.cache_hit is True
    assert second.cache_key == first.cache_key
    assert len(command_calls) == first_call_count

    source.write_bytes(b"second-snapshot")
    third = graph_module.load_or_build_osm_graph(source, boundary, tmp_path / "cache")

    assert third.cache_hit is False
    assert third.cache_key != first.cache_key
    assert len(command_calls) > first_call_count
