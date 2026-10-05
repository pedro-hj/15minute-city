from __future__ import annotations

import shutil
import subprocess

import geopandas as gpd
import pytest
from shapely.geometry import box

from fifteen_minute_city.infrastructure.osm.graph import load_or_build_osm_graph
from fifteen_minute_city.infrastructure.osm.services import load_services_from_pbf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("osmium") is None, reason="osmium is unavailable"),
]


def test_graph_and_services_are_loaded_from_a_local_pbf(tmp_path) -> None:
    source_xml = tmp_path / "source.osm"
    source_pbf = tmp_path / "source.osm.pbf"
    source_xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="integration-test">
  <node id="101" lat="0.000" lon="0.000" />
  <node id="102" lat="0.000" lon="0.001" />
  <node id="103" lat="0.000" lon="0.002" />
  <node id="201" lat="0.0001" lon="0.0001">
    <tag k="amenity" v="hospital" />
    <tag k="name" v="Hospital Teste" />
  </node>
  <way id="501">
    <nd ref="101" />
    <nd ref="102" />
    <nd ref="103" />
    <tag k="highway" v="residential" />
  </way>
</osm>
""",
        encoding="utf-8",
    )
    subprocess.run(
        ["osmium", "cat", str(source_xml), "-o", str(source_pbf)],
        check=True,
        capture_output=True,
        text=True,
    )
    boundary = gpd.GeoDataFrame(
        {"geometry": [box(-0.01, -0.01, 0.01, 0.01)]},
        crs="EPSG:4326",
    )

    artifact = load_or_build_osm_graph(source_pbf, boundary, tmp_path / "cache")
    services = load_services_from_pbf(
        artifact.graph,
        artifact.region_pbf_path,
        {"health": [("amenity", "hospital")]},
    )

    assert {101, 103}.issubset(artifact.graph.nodes)
    assert services.nodes_by_category["health"]
    assert services.services_by_category["health"][0].name == "Hospital Teste"
    assert services.services_by_category["health"][0].graph_node_id in artifact.graph
