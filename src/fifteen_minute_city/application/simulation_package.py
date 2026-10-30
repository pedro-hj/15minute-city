"""Portable, versioned routing-data bundles for client-side simulations.

The .fmc format contains a reverse CSR adjacency graph and per-node analysis
data. It is intentionally independent of Python and can be read by JS, WASM,
or a native client. All floating-point arrays use little-endian float64.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import re
import struct
import sys
from array import array
from pathlib import Path

import networkx as nx
import osmnx as ox
from sqlalchemy import select
from sqlalchemy.orm import Session

from fifteen_minute_city.db.connection import session_scope
from fifteen_minute_city.db.models.category import ServiceCategory
from fifteen_minute_city.db.models.execution import Execution
from fifteen_minute_city.db.models.metrics import CityIndex, NodeReachability
from fifteen_minute_city.db.models.node import Node

MAGIC = b"FMC1"
HEADER = struct.Struct("<4sIIII")
MAX_U32 = 2**32 - 1


def build_package(
    graph: nx.MultiDiGraph,
    *,
    execution_id: int,
    speed_kmh: float,
    threshold_minutes: float,
    categories: list[str],
    population_by_osm: dict[int, float],
    baseline_minutes: dict[tuple[int, str], float | None],
    pbf_checksum: str,
    graph_cache_key: str,
) -> bytes:
    """Encode the graph and baseline node times as a platform-neutral bundle."""
    if sys.byteorder != "little":
        raise RuntimeError("This exporter currently requires little-endian Python")
    if not graph.is_directed():
        raise ValueError("The cached walking graph must be directed")
    if not (math.isfinite(speed_kmh) and speed_kmh > 0):
        raise ValueError("speed_kmh must be a positive finite value")
    if not (math.isfinite(threshold_minutes) and threshold_minutes > 0):
        raise ValueError("threshold_minutes must be positive and finite")
    if not categories or len(set(categories)) != len(categories):
        raise ValueError("A non-empty set of unique categories is required")

    nodes = list(graph.nodes)
    count = len(nodes)
    if not count or count > MAX_U32:
        raise ValueError("Graph has an unsupported number of nodes")
    if set(population_by_osm) != set(nodes):
        raise ValueError("Population lookup must cover exactly the cached graph nodes")
    expected = count * len(categories)
    if len(baseline_minutes) != expected:
        raise ValueError("Missing baseline node/category records")
    positions = {node_id: index for index, node_id in enumerate(nodes)}

    coordinates = array("d")
    population = array("d")
    baseline = array("d")
    for node_id in nodes:
        data = graph.nodes[node_id]
        longitude = float(data["x"])
        latitude = float(data["y"])
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("Invalid graph coordinate")
        coordinates.extend((longitude, latitude))
        weight = float(population_by_osm[node_id])
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("Population must be finite and non-negative")
        population.append(weight)
        for category in categories:
            minutes = baseline_minutes[(node_id, category)]
            if minutes is None:
                baseline.append(math.inf)
            elif math.isfinite(minutes) and minutes >= 0:
                baseline.append(minutes * 60.0)
            else:
                raise ValueError("Baseline times must be non-negative and finite")

    # Dijkstra from service nodes must follow the REVERSED directed graph:
    # an original edge u -> v becomes a CSR edge v -> u.
    neighbors: list[list[tuple[int, float]]] = [[] for _ in range(count)]
    edge_count = 0
    for origin, target, attributes in graph.edges(data=True):
        length = float(attributes["length"])
        if not math.isfinite(length) or length < 0:
            raise ValueError("Graph edge length is invalid")
        seconds = round(length * 3.6 / speed_kmh, 1)
        neighbors[positions[target]].append((positions[origin], seconds))
        edge_count += 1
    if edge_count > MAX_U32:
        raise ValueError("Graph has too many edges for FMC1")

    offsets = array("I", [0])
    targets = array("I")
    durations = array("d")
    for entries in neighbors:
        for target, duration in entries:
            targets.append(target)
            durations.append(duration)
        offsets.append(len(targets))

    metadata = {
        "format_version": 1,
        "execution_id": execution_id,
        "categories": categories,
        "threshold_minutes": threshold_minutes,
        "speed_kmh": speed_kmh,
        "pbf_checksum": pbf_checksum,
        "graph_cache_key": graph_cache_key,
        "population_total": float(sum(population)),
        "routing": "reversed-directed-csr",
        "distance_unit": "seconds",
        "coordinate_system": "EPSG:4326",
    }
    meta_bytes = json.dumps(
        metadata, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    result = io.BytesIO()
    result.write(HEADER.pack(MAGIC, len(meta_bytes), count, edge_count, len(categories)))
    result.write(meta_bytes)
    result.write(b"\0" * (-result.tell() % 8))
    for values in (coordinates, population, baseline, offsets, targets, durations):
        result.write(values.tobytes())
    return result.getvalue()


def export_completed_execution(
    db: Session,
    execution_id: int,
    *,
    cache_dir: Path,
    output_dir: Path,
) -> Path:
    """Build a package once on the VPS, using its existing GraphML and database."""
    execution = db.get(Execution, execution_id)
    if execution is None or execution.status != "completed":
        raise ValueError("The execution must exist and be completed")

    metadata = execution.analysis_metadata or {}
    cache_key = metadata.get("graph_cache_key")
    checksum = execution.pbf_checksum or metadata.get("pbf_checksum")
    if not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Completed execution lacks a valid PBF checksum")
    if not isinstance(cache_key, str) or not re.fullmatch(r"[a-f0-9]{24}", cache_key):
        raise ValueError("Completed execution lacks a valid graph cache key")
    graph_dir = cache_dir.resolve() / checksum / cache_key
    graph_file = graph_dir / "graph.graphml"
    cache_metadata_file = graph_dir / "metadata.json"
    if not graph_file.is_file() or not cache_metadata_file.is_file():
        raise FileNotFoundError("Versioned GraphML cache is unavailable for this execution")
    cache_meta = json.loads(cache_metadata_file.read_text(encoding="utf-8"))
    if cache_meta.get("pbf_checksum") != checksum or cache_meta.get("network_type") != execution.network_type:
        raise ValueError("Cached graph does not match the stored execution")

    graph = ox.load_graphml(graph_file)
    node_rows = db.execute(
        select(Node.osm_id, Node.population_weight).where(Node.execution_id == execution_id)
    ).all()
    weights = {
        int(osm_id): float(weight or 0.0) for osm_id, weight in node_rows
    }
    if not node_rows or not any(weight is not None for _, weight in node_rows):
        raise ValueError(
            "This execution predates population-weight persistence; rerun its analysis"
        )
    summary = db.execute(
        select(CityIndex.total_weight).where(
            CityIndex.execution_id == execution_id,
            CityIndex.origin_strategy == "population_grid",
        )
    ).first()
    if summary is None:
        raise ValueError("This execution has no population-weighted analysis")
    if not math.isclose(
        sum(weights.values()), float(summary[0]), rel_tol=1e-8, abs_tol=1e-5
    ):
        raise ValueError("Population totals do not match the saved analysis")

    categories = db.execute(
        select(ServiceCategory.code)
        .join(CityIndex, CityIndex.category_id == ServiceCategory.id)
        .where(
            CityIndex.execution_id == execution_id,
            CityIndex.origin_strategy == "network_nodes",
        )
        .order_by(ServiceCategory.code)
    ).scalars().all()
    if not categories:
        raise ValueError("There are no persisted categories for this execution")
    times = {}
    for osm_id, code, minutes in db.execute(
        select(
            Node.osm_id,
            ServiceCategory.code,
            NodeReachability.travel_time_minutes,
        )
        .join(NodeReachability, NodeReachability.node_id == Node.id)
        .join(ServiceCategory, ServiceCategory.id == NodeReachability.category_id)
        .where(Node.execution_id == execution_id)
    ):
        times[(int(osm_id), code)] = float(minutes) if minutes is not None else None

    bundle = build_package(
        graph,
        execution_id=execution_id,
        speed_kmh=execution.speed_kmh,
        threshold_minutes=execution.threshold_minutes,
        categories=list(categories),
        population_by_osm=weights,
        baseline_minutes=times,
        pbf_checksum=checksum,
        graph_cache_key=cache_key,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{execution_id}.fmc.gz"
    temporary_path = output_dir / f".{execution_id}.fmc.gz.tmp"
    with (
        temporary_path.open("wb") as destination,
        gzip.GzipFile(fileobj=destination, mode="wb", mtime=0) as zipped,
    ):
        zipped.write(bundle)
    temporary_path.replace(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a portable simulation bundle for a completed execution"
    )
    parser.add_argument("--execution-id", type=int, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/simulation-packages")
    )
    args = parser.parse_args()
    if args.execution_id <= 0:
        parser.error("--execution-id must be positive")
    with session_scope() as session:
        path = export_completed_execution(
            session,
            args.execution_id,
            cache_dir=args.cache_dir,
            output_dir=args.output_dir,
        )
    print(f"Simulation package ready: {path}")


if __name__ == "__main__":
    main()
