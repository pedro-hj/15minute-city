"""Database-backed smoke test for the current accessibility pipeline."""

import time

import networkx as nx
from shapely.geometry import Point

from fifteen_minute_city.application.analysis_runner import AccessibilityAnalysisRunner
from fifteen_minute_city.db.pipelines import AlgorithmPipeline


def main() -> None:
    started_at = time.perf_counter()
    pipeline = AlgorithmPipeline()
    context = pipeline.prepare_execution(
        city_name="Paris",
        country="France",
        speed_kmh=3.0,
        threshold_minutes=15.0,
    )

    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(99001, x=2.3522, y=48.8566)
    graph.add_node(99002, x=2.3523, y=48.8567)
    graph.add_edge(99001, 99002, travel_time=120.0)
    graph.add_edge(99002, 99001, travel_time=120.0)
    node_map = pipeline.save_graph_nodes(context.execution_id, graph)

    organized_services = {
        category.code: [
            [
                f"Synthetic {category.display_name}",
                99001,
                Point(2.3522, 48.8566),
            ]
        ]
        for category in context.categories
    }
    pipeline.save_services_from_organizer(
        context.execution_id,
        organized_services,
        osm_to_db_node_map=node_map,
    )

    outcome = AccessibilityAnalysisRunner(threshold_minutes=15.0).run(
        graph,
        {category.code: [99001] for category in context.categories},
        include_details=True,
    )
    pipeline.save_accessibility_outcome(
        context.execution_id,
        outcome,
        graph_node_to_db_id=node_map,
        processing_time_seconds=time.perf_counter() - started_at,
    )
    print(
        "Pipeline smoke test completed: "
        f"execution={context.execution_id}, score={outcome.primary_report.overall_score}"
    )


if __name__ == "__main__":
    main()
