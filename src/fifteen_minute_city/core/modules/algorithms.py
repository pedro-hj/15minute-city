from __future__ import annotations

import logging

import networkx as nx
import pandas as pd

logger = logging.getLogger(__name__)


def multi_source_algorithm(
    G: nx.MultiDiGraph,
    points: dict[list],
    execution_id: int | None = None,
    pipeline=None,
    runtime_seconds: float | None = None,
) -> list:
    result = []
    for tag, points_list in points.items():
        time = nx.multi_source_dijkstra_path_length(
            G, sources=points_list, weight="travel_time"
        )
        serie_times = pd.Series(time)
        data = {
            "service": tag,
            "qtd_nodes": int(serie_times.count()),
            "mean": float(serie_times.mean()) / 60,
            "median": float(serie_times.median()) / 60,
            "max": float(serie_times.max()) / 60,
            "std": float(serie_times.std()) / 60,
        }
        # PERSISTENCE POINT: "data" -> "alcancabilidade_no" TABLE, "indice_cidade" TABLE
        result.append(data)

    if pipeline and execution_id:
        try:
            pipeline.save_algorithm_metrics(
                execution_id=execution_id,
                metrics_list=result,
                processing_time_seconds=runtime_seconds,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("Database metrics persistence skipped: %s", e)

    return result
