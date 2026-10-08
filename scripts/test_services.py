"""Database service smoke test using the scientific accessibility report."""

import networkx as nx

from fifteen_minute_city.db.connection import session_scope
from fifteen_minute_city.db.services import (
    bulk_save_node_reachabilities,
    bulk_save_nodes,
    bulk_save_services,
    create_execution,
    get_city_indices_for_execution,
    get_or_create_city,
    save_accessibility_report,
    seed_default_categories,
    update_execution_status,
)
from fifteen_minute_city.domain.models import Origin, OriginSet
from fifteen_minute_city.domain.reachability import analyze_accessibility


def main() -> None:
    with session_scope() as db:
        city = get_or_create_city(
            db,
            name="Praia Grande",
            country="Brazil",
            geom_boundary_geojson={
                "type": "Polygon",
                "coordinates": [
                    [
                        [-46.41, -24.01],
                        [-46.40, -24.01],
                        [-46.40, -24.00],
                        [-46.41, -24.00],
                        [-46.41, -24.01],
                    ]
                ],
            },
        )
        categories = seed_default_categories(db)
        execution = create_execution(
            db,
            city_id=city.id,
            speed_kmh=3.0,
            threshold_minutes=15.0,
        )

        node_map = bulk_save_nodes(
            db,
            execution.id,
            [
                {"osm_id": 10001, "lat": -24.005, "lon": -46.405},
                {"osm_id": 10002, "lat": -24.006, "lon": -46.406},
            ],
        )
        services = bulk_save_services(
            db,
            execution.id,
            [
                {
                    "category_id": category.id,
                    "name": f"Synthetic {category.display_name}",
                    "lat": -24.0051,
                    "lon": -46.4051,
                    "representative_node_id": node_map[10001],
                }
                for category in categories
            ],
        )

        graph = nx.MultiDiGraph()
        graph.add_edge(10001, 10002, travel_time=120.0)
        graph.add_edge(10002, 10001, travel_time=120.0)
        origins = OriginSet(
            strategy="network_nodes",
            weight_unit="node_count",
            origins=(
                Origin("node:10001", 10001, 1.0),
                Origin("node:10002", 10002, 1.0),
            ),
        )
        report = analyze_accessibility(
            graph,
            {category.code: [10001] for category in categories},
            origins,
            include_details=True,
        )
        category_id_map = {category.code: category.id for category in categories}
        service_id_map = {service.category_id: service.id for service in services}
        reachability_rows = []
        for code, metrics in report.categories.items():
            category_id = category_id_map[code]
            for detail in metrics.details:
                reachability_rows.append(
                    {
                        "node_id": node_map[detail.node_id],
                        "category_id": category_id,
                        "closest_service_id": service_id_map[category_id],
                        "travel_time_minutes": detail.travel_time_minutes,
                        "reachable": detail.reachable,
                        "within_threshold": detail.within_threshold,
                    }
                )

        bulk_save_node_reachabilities(db, reachability_rows)
        save_accessibility_report(db, execution.id, report, category_id_map)
        indices = get_city_indices_for_execution(db, execution.id)
        update_execution_status(
            db,
            execution.id,
            status="completed",
            execution_time_seconds=1.25,
        )
        db.commit()
        print(
            f"Database smoke test completed: execution={execution.id}, "
            f"indices={len(indices)}, score={report.overall_score}"
        )


if __name__ == "__main__":
    main()
