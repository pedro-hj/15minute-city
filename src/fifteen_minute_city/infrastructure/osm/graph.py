from __future__ import annotations

import hashlib
import json
import subprocess
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely import normalize

GRAPH_BUILDER_VERSION = "osm-xml-v2"
WALK_HIGHWAYS = [
    "footway",
    "pedestrian",
    "steps",
    "path",
    "living_street",
    "residential",
    "service",
    "unclassified",
    "tertiary",
    "secondary",
    "primary",
]
_ALLOWED_FOOT = {"yes", "designated", "permissive", "destination"}
_DENIED_FOOT = {"no", "private", "use_sidepath"}
_DENIED_ACCESS = {"no", "private"}


@dataclass(frozen=True, slots=True)
class OSMGraphArtifact:
    graph: nx.MultiDiGraph
    region_pbf_path: str
    cache_key: str
    pbf_checksum: str
    cache_hit: bool


def _run_osmium(arguments: list[str]) -> None:
    try:
        subprocess.run(
            ["osmium", *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "osmium-tool is required to process local PBF files"
        ) from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or error.stdout.strip() or str(error)
        raise RuntimeError(f"osmium failed: {message}") from error


def _tag_values(value: object) -> set[str]:
    if value is None:
        return set()
    values = value if isinstance(value, list) else [value]
    return {str(item).strip().lower() for item in values}


def _remove_non_walkable_edges(graph: nx.MultiDiGraph) -> None:
    """Remove explicitly forbidden pedestrian links from the graph."""
    edges_to_remove = []
    for origin, destination, key, data in graph.edges(keys=True, data=True):
        foot_values = _tag_values(data.get("foot"))
        access_values = _tag_values(data.get("access"))
        explicitly_walkable = bool(foot_values & _ALLOWED_FOOT)
        forbidden = bool(foot_values & _DENIED_FOOT) or bool(
            access_values & _DENIED_ACCESS
        )
        if forbidden and not explicitly_walkable:
            edges_to_remove.append((origin, destination, key))

    graph.remove_edges_from(edges_to_remove)
    graph.remove_nodes_from(list(nx.isolates(graph)))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a stable content identity without loading the entire file in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _cached_pbf_checksum(path: str, size: int, mtime_ns: int) -> str:
    return sha256_file(Path(path))


def _boundary_digest(boundary: gpd.GeoDataFrame) -> str:
    """Calculate a stable identity for a municipality boundary."""
    boundary_wgs84 = boundary.to_crs("EPSG:4326")
    digest = hashlib.sha256()
    for geometry in boundary_wgs84.geometry:
        digest.update(normalize(geometry).wkb)
    return digest.hexdigest()


def load_or_build_osm_graph(
    pbf_path: str | Path,
    boundary: gpd.GeoDataFrame,
    cache_dir: str | Path,
    network_type: str = "walk",
) -> OSMGraphArtifact:
    """Load a versioned graph cache or build a graph preserving OSM node IDs."""
    if network_type != "walk":
        raise ValueError("only the 'walk' network type is currently supported")

    source_path = Path(pbf_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"OSM PBF file not found: {source_path}")
    if boundary.empty:
        raise ValueError("the region boundary must not be empty")
    if boundary.crs is None:
        raise ValueError("the region boundary must define a CRS")

    stat = source_path.stat()
    pbf_checksum = _cached_pbf_checksum(
        str(source_path), stat.st_size, stat.st_mtime_ns
    )
    cache_parameters = {
        "builder": GRAPH_BUILDER_VERSION,
        "pbf_checksum": pbf_checksum,
        "network_type": network_type,
        "boundary_checksum": _boundary_digest(boundary),
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_parameters, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]

    root = Path(cache_dir).expanduser().resolve() / pbf_checksum
    entry_dir = root / cache_key
    graph_path = entry_dir / "graph.graphml"
    region_pbf_path = entry_dir / "region.osm.pbf"
    metadata_path = entry_dir / "metadata.json"

    if graph_path.is_file() and region_pbf_path.is_file() and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata == cache_parameters:
            graph = ox.load_graphml(graph_path)
            return OSMGraphArtifact(
                graph,
                str(region_pbf_path),
                cache_key,
                pbf_checksum,
                True,
            )

    entry_dir.mkdir(parents=True, exist_ok=True)
    boundary_path = entry_dir / "boundary.geojson"
    filtered_pbf_path = entry_dir / "walk.osm.pbf"
    filtered_xml_path = entry_dir / "walk.osm"
    boundary[["geometry"]].to_file(boundary_path, driver="GeoJSON")

    _run_osmium(
        [
            "extract",
            "-p",
            str(boundary_path),
            str(source_path),
            "-o",
            str(region_pbf_path),
            "--overwrite",
        ]
    )
    _run_osmium(
        [
            "tags-filter",
            str(region_pbf_path),
            f"w/highway={','.join(WALK_HIGHWAYS)}",
            "-o",
            str(filtered_pbf_path),
            "--overwrite",
        ]
    )
    _run_osmium(
        [
            "cat",
            str(filtered_pbf_path),
            "-o",
            str(filtered_xml_path),
            "--overwrite",
        ]
    )

    original_useful_tags = ox.settings.useful_tags_way
    if "foot" not in original_useful_tags:
        ox.settings.useful_tags_way = [*original_useful_tags, "foot"]
    try:
        graph = ox.graph_from_xml(
            filtered_xml_path,
            bidirectional=True,
            simplify=False,
            retain_all=True,
        )
    finally:
        ox.settings.useful_tags_way = original_useful_tags

    _remove_non_walkable_edges(graph)
    if graph.number_of_edges() == 0:
        raise ValueError("the extracted walking graph is empty")
    if not graph.graph.get("simplified", False):
        graph = ox.simplification.simplify_graph(graph)
    ox.save_graphml(graph, graph_path)
    metadata_path.write_text(
        json.dumps(cache_parameters, indent=2),
        encoding="utf-8",
    )
    boundary_path.unlink(missing_ok=True)
    filtered_pbf_path.unlink(missing_ok=True)
    filtered_xml_path.unlink(missing_ok=True)

    return OSMGraphArtifact(
        graph,
        str(region_pbf_path),
        cache_key,
        pbf_checksum,
        False,
    )
