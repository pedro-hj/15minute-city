"""Server-side FMC1 simulation engine: immutable cached data and incremental routing."""

from __future__ import annotations

import gzip
import heapq
import json
import math
import struct
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
EARTH_RADIUS_M = 6371008.8
RAD = math.pi / 180


class InvalidSimulationPackage(ValueError):
    """The stored FMC1 bundle cannot be used."""


class InvalidSimulationRequest(ValueError):
    """The hypothetical service cannot be attached to the network."""


@dataclass(frozen=True)
class SimulationBundle:
    metadata: dict
    coordinates: np.ndarray
    population: np.ndarray
    baseline: np.ndarray
    offsets: np.ndarray
    targets: np.ndarray
    travel_time: np.ndarray
    baseline_metrics: dict

    @property
    def node_count(self) -> int:
        return len(self.population)


def decode_package(raw: bytes) -> SimulationBundle:
    """Read and validate FMC1 without rebuilding a NetworkX graph."""
    if len(raw) < 20:
        raise InvalidSimulationPackage("FMC1 header is missing")
    magic, meta_len, n, m, k = struct.unpack_from("<4sIIII", raw)
    if magic != b"FMC1" or not n or not 1 <= k <= 32:
        raise InvalidSimulationPackage("Invalid FMC1 header")
    start = (20 + meta_len + 7) // 8 * 8
    expected = start + 8 * (3 * n + n * k) + 4 * (n + 1) + 12 * m
    if start > len(raw) or expected != len(raw):
        raise InvalidSimulationPackage("Invalid FMC1 length")
    try:
        meta = json.loads(raw[20 : 20 + meta_len])
        codes = meta["categories"]
        threshold = float(meta["threshold_minutes"])
        if (
            meta["format_version"] != 1
            or not isinstance(codes, list)
            or len(codes) != k
            or any(not isinstance(code, str) or not code for code in codes)
            or len(set(codes)) != k
            or not math.isfinite(threshold)
            or threshold <= 0
        ):
            raise ValueError("Invalid metadata")
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidSimulationPackage("Invalid FMC1 metadata") from exc

    pos = start

    def take(dtype: str, count: int) -> np.ndarray:
        nonlocal pos
        values = np.frombuffer(raw, dtype=dtype, count=count, offset=pos)
        pos += values.nbytes
        return values

    coordinates = take("<f8", 2 * n).reshape((n, 2))
    population = take("<f8", n)
    baseline = take("<f8", n * k).reshape((n, k))
    offsets = take("<u4", n + 1)
    targets = take("<u4", m)
    travel_time = take("<f8", m)

    if (
        not np.isfinite(coordinates).all()
        or np.any(np.abs(coordinates[:, 0]) > 180)
        or np.any(np.abs(coordinates[:, 1]) > 90)
        or not np.isfinite(population).all()
        or np.any(population < 0)
        or population.sum() <= 0
        or np.isnan(baseline).any()
        or np.isneginf(baseline).any()
        or np.any(baseline < 0)
        or offsets[0] != 0
        or offsets[-1] != m
        or np.any(offsets[:-1] > offsets[1:])
        or np.any(targets >= n)
        or not np.isfinite(travel_time).all()
        or np.any(travel_time < 0)
    ):
        raise InvalidSimulationPackage("Invalid FMC1 graph or measurements")

    bundle = SimulationBundle(
        metadata=meta,
        coordinates=coordinates,
        population=population,
        baseline=baseline,
        offsets=offsets,
        targets=targets,
        travel_time=travel_time,
        baseline_metrics={},
    )
    baseline_metrics = {
        "population": _metrics(bundle, {}, weighted=True),
        "nodes": _metrics(bundle, {}, weighted=False),
    }
    object.__setattr__(bundle, "baseline_metrics", baseline_metrics)
    return bundle


@lru_cache(maxsize=2)
def _load_cached(path: str, modified_ns: int, size: int) -> SimulationBundle:
    """Cache by path and file version; limit decompressed input size."""
    del modified_ns, size
    with gzip.open(path, "rb") as file:
        raw = file.read(MAX_UNCOMPRESSED_BYTES + 1)
    if len(raw) > MAX_UNCOMPRESSED_BYTES:
        raise InvalidSimulationPackage("FMC1 file exceeds the server memory limit")
    return decode_package(raw)


def load_execution_package(folder: Path, execution_id: int) -> SimulationBundle:
    """Load only pre-generated completed-execution bundles."""
    if execution_id <= 0:
        raise InvalidSimulationRequest("Execution ID must be positive")
    path = folder / f"{execution_id}.fmc.gz"
    stats = path.stat()
    bundle = _load_cached(str(path.resolve()), stats.st_mtime_ns, stats.st_size)
    if bundle.metadata.get("execution_id") != execution_id:
        raise InvalidSimulationPackage("FMC1 execution ID mismatch")
    return bundle


def _nearest(bundle: SimulationBundle, longitude: float, latitude: float) -> tuple[int, float]:
    coords = bundle.coordinates
    dx = (longitude - coords[:, 0]) * RAD * np.cos(
        (latitude + coords[:, 1]) * RAD / 2
    )
    dy = (latitude - coords[:, 1]) * RAD
    distances = EARTH_RADIUS_M * np.hypot(dx, dy)
    index = int(np.argmin(distances))
    return index, float(distances[index])


def _dijkstra(bundle: SimulationBundle, sources: set[int]) -> np.ndarray:
    distances = np.full(bundle.node_count, math.inf, dtype=np.float64)
    heap: list[tuple[float, int]] = []
    for index in sources:
        distances[index] = 0.0
        heapq.heappush(heap, (0.0, index))

    offsets, targets, durations = bundle.offsets, bundle.targets, bundle.travel_time
    while heap:
        distance, node = heapq.heappop(heap)
        if distance > distances[node]:
            continue
        for edge in range(int(offsets[node]), int(offsets[node + 1])):
            adjacent = int(targets[edge])
            new_distance = distance + float(durations[edge])
            if new_distance < distances[adjacent]:
                distances[adjacent] = new_distance
                heapq.heappush(heap, (new_distance, adjacent))
    return distances


def _weighted_median_minutes(times: np.ndarray, weights: np.ndarray) -> float | None:
    positive = np.isfinite(times) & (weights > 0)
    if not positive.any():
        return None
    values = times[positive]
    counts = weights[positive]
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(counts[order])
    halfway = float(counts.sum()) / 2
    position = min(int(np.searchsorted(cumulative, halfway, side="left")), len(order) - 1)
    return float(values[order[position]] / 60)


def _metrics(bundle: SimulationBundle, updates: dict[int, np.ndarray], *, weighted: bool) -> dict:
    weights = bundle.population if weighted else np.ones(bundle.node_count)
    total = float(weights.sum())
    if total <= 0:
        raise InvalidSimulationPackage("No population weights")
    threshold = float(bundle.metadata["threshold_minutes"]) * 60
    within_all = np.ones(bundle.node_count, dtype=bool)
    unreachable_any = np.zeros(bundle.node_count, dtype=bool)
    categories: dict[str, dict] = {}
    for index, code in enumerate(bundle.metadata["categories"]):
        original = bundle.baseline[:, index]
        times = np.minimum(original, updates[index]) if index in updates else original
        reachable = np.isfinite(times)
        within = times <= threshold
        within_all &= within
        unreachable_any |= ~reachable
        reachable_weight = float(weights[reachable].sum())
        categories[code] = {
            "coverage_percentage": 100 * float(weights[within].sum()) / total,
            "unreachable_percentage": 100 * (total - reachable_weight) / total,
            "mean_travel_time_minutes": (
                float(np.dot(times[reachable], weights[reachable]) / (reachable_weight * 60))
                if reachable_weight
                else None
            ),
            "median_travel_time_minutes": _weighted_median_minutes(times, weights),
        }
    return {
        "categories": categories,
        "overall_coverage_percentage": 100 * float(weights[within_all].sum()) / total,
        "overall_unreachable_percentage": (
            100 * float(weights[unreachable_any].sum()) / total
        ),
    }


def _delta(baseline: dict, simulated: dict) -> dict:
    return {
        "unit": "percentage_points",
        "category_coverage": {
            code: simulated["categories"][code]["coverage_percentage"]
            - values["coverage_percentage"]
            for code, values in baseline["categories"].items()
        },
        "overall_coverage": (
            simulated["overall_coverage_percentage"]
            - baseline["overall_coverage_percentage"]
        ),
    }


def simulate(
    bundle: SimulationBundle,
    services: list[dict],
    *,
    max_snap_distance_m: float = 250,
) -> dict:
    """Simulate hypothetical services without mutating original data."""
    started = time.perf_counter()
    if not 1 <= len(services) <= 200:
        raise InvalidSimulationRequest("Expected 1 to 200 hypothetical services")
    if not math.isfinite(max_snap_distance_m) or max_snap_distance_m <= 0:
        raise InvalidSimulationRequest("Invalid snapping distance")

    categories = bundle.metadata["categories"]
    sources: dict[int, set[int]] = {}
    placed: list[dict] = []
    for service in services:
        category = service["category"]
        if category not in categories:
            raise InvalidSimulationRequest(f"Category not analyzed: {category}")
        lon, lat = float(service["longitude"]), float(service["latitude"])
        if not math.isfinite(lon) or not math.isfinite(lat) or abs(lon) > 180 or abs(lat) > 90:
            raise InvalidSimulationRequest("Invalid geographic coordinates")
        node, metres = _nearest(bundle, lon, lat)
        if metres > max_snap_distance_m:
            raise InvalidSimulationRequest(
                f"Service too far from walking network: {metres:.1f} m"
            )
        sources.setdefault(categories.index(category), set()).add(node)
        placed.append({
            "name": service.get("name"),
            "category": category,
            "longitude": lon,
            "latitude": lat,
            "graph_node_index": node,
            "snap_distance_m": metres,
        })

    updates = {category: _dijkstra(bundle, nodes) for category, nodes in sources.items()}
    baseline = bundle.baseline_metrics
    simulated = {
        "population": _metrics(bundle, updates, weighted=True),
        "nodes": _metrics(bundle, updates, weighted=False),
    }
    return {
        "execution_id": bundle.metadata["execution_id"],
        "added_services": placed,
        "baseline": baseline,
        "simulated": simulated,
        "delta": {
            "population": _delta(baseline["population"], simulated["population"]),
            "nodes": _delta(baseline["nodes"], simulated["nodes"]),
        },
        "processing_time_ms": round((time.perf_counter() - started) * 1000, 3),
    }
