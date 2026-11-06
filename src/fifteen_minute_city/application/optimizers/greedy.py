from __future__ import annotations

import heapq
import math
import time

import numpy as np

from fifteen_minute_city.application.optimizers.base import (
    BaseLocationOptimizer,
    OptimizationResult,
    ProposedLocation,
)
from fifteen_minute_city.application.server_simulation import (
    EARTH_RADIUS_M,
    RAD,
    SimulationBundle,
)


def _dijkstra_within_threshold(
    bundle: SimulationBundle,
    source_node: int,
    max_seconds: float,
) -> dict[int, float]:
    """Calculate walking times from source_node, stopping at max_seconds."""
    distances: dict[int, float] = {source_node: 0.0}
    heap: list[tuple[float, int]] = [(0.0, source_node)]

    offsets = bundle.offsets
    targets = bundle.targets
    durations = bundle.travel_time
    while heap:
        distance, node = heapq.heappop(heap)
        if distance > max_seconds:
            break
        if distance > distances[node]:
            continue
        for edge in range(int(offsets[node]), int(offsets[node + 1])):
            adjacent = int(targets[edge])
            new_distance = distance + float(durations[edge])
            if new_distance <= max_seconds and (
                adjacent not in distances or new_distance < distances[adjacent]
            ):
                distances[adjacent] = new_distance
                heapq.heappush(heap, (new_distance, adjacent))
    return distances


def _haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate geographical distance in meters between two points on Earth."""
    dx = (lon2 - lon1) * RAD * math.cos((lat1 + lat2) * RAD / 2)
    dy = (lat2 - lat1) * RAD
    return float(EARTH_RADIUS_M * math.hypot(dx, dy))


class GreedyLocationOptimizer(BaseLocationOptimizer):
    """greedy optimizer for service allocation based on population marginal gain."""

    def optimize(
        self,
        bundle: SimulationBundle,
        category: str,
        k: int = 1,
        *,
        threshold_minutes: float | None = None,
        min_distance_m: float = 0.0,
        candidate_pool: list[int] | None = None,
    ) -> OptimizationResult:
        start_time = time.perf_counter()
        # 1. Validações de entrada
        if k < 1:
            raise ValueError(f"k must be at least 1, got {k}")
        categories = bundle.metadata.get("categories", [])
        if category not in categories:
            raise ValueError(
                f"Category '{category}' not found in bundle. Available: {categories}"
            )
        category_index = categories.index(category)
        # 2. Configurações de tempo e população
        threshold_sec = (
            threshold_minutes * 60.0
            if threshold_minutes is not None
            else float(bundle.metadata["threshold_minutes"]) * 60.0
        )
        total_population = float(bundle.population.sum())
        if total_population <= 0:
            raise ValueError("Bundle has no valid population")
        # 3. Estado de cobertura atual (baseline)
        baseline_times = bundle.baseline[:, category_index]
        currently_covered = baseline_times <= threshold_sec
        baseline_coverage_pct = (
            100.0 * float(bundle.population[currently_covered].sum()) / total_population
        )
        # 4. Seleção do espaço de candidatos
        if candidate_pool is not None:
            candidates = set(candidate_pool)
        else:
            # Por padrão: nós desatendidos com população residente positiva
            unserved_nodes = np.where((~currently_covered) & (bundle.population > 0))[0]
            candidates = {int(n) for n in unserved_nodes}
        proposed: list[ProposedLocation] = []
        selected_nodes: list[int] = []
        # 5. Loop Guloso para encontrar k pontos
        for rank in range(1, k + 1):
            best_node: int | None = None
            best_gain = -1.0
            best_reached_nodes: dict[int, float] = {}
            for candidate in candidates:
                # Restrição de distância mínima em relação aos já selecionados
                if min_distance_m > 0 and selected_nodes:
                    c_lon, c_lat = (
                        bundle.coordinates[candidate, 0],
                        bundle.coordinates[candidate, 1],
                    )
                    too_close = any(
                        _haversine_distance_m(
                            c_lat,
                            c_lon,
                            bundle.coordinates[sel, 1],
                            bundle.coordinates[sel, 0],
                        )
                        < min_distance_m
                        for sel in selected_nodes
                    )
                    if too_close:
                        continue
                # Dijkstra podado aos 15 minutos
                reached = _dijkstra_within_threshold(bundle, candidate, threshold_sec)
                # Ganho Marginal: soma da população de nós alcançados que AINDA NÃO estão cobertos
                marginal_pop = 0.0
                for node_id in reached:
                    if not currently_covered[node_id]:
                        marginal_pop += float(bundle.population[node_id])
                if marginal_pop > best_gain:
                    best_gain = marginal_pop
                    best_node = candidate
                    best_reached_nodes = reached
            # Se não encontrou nenhum candidato viável ou o ganho for zero, encerra
            if best_node is None or best_gain <= 0:
                break
            # Registra o ponto escolhido
            best_lon, best_lat = (
                float(bundle.coordinates[best_node, 0]),
                float(bundle.coordinates[best_node, 1]),
            )
            proposed.append(
                ProposedLocation(
                    rank=rank,
                    node_id=best_node,
                    latitude=best_lat,
                    longitude=best_lon,
                    marginal_population=best_gain,
                )
            )
            # Atualiza o estado: nós recém-atendidos agora estão cobertos
            selected_nodes.append(best_node)
            candidates.discard(best_node)
            for node_id in best_reached_nodes:
                currently_covered[node_id] = True
        # 6. Cálculo da cobertura final simulada
        simulated_coverage_pct = (
            100.0 * float(bundle.population[currently_covered].sum()) / total_population
        )
        elapsed_seconds = time.perf_counter() - start_time
        return OptimizationResult(
            strategy="greedy",
            category=category,
            locations=tuple(proposed),
            baseline_coverage_percentage=baseline_coverage_pct,
            simulated_coverage_percentage=simulated_coverage_pct,
            execution_time_seconds=elapsed_seconds,
        )
