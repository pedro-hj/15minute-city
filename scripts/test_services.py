"""
Integration test script verifying modular database services against Aiven PostgreSQL.
"""

import sys
from fifteen_minute_city.db.connection import get_db
from fifteen_minute_city.db.services import (
    get_or_create_city,
    seed_default_categories,
    create_execution,
    update_execution_status,
    bulk_save_nodes,
    bulk_save_services,
    bulk_save_node_reachabilities,
    save_city_indices,
    get_city_indices_for_execution,
)


def main():
    print("Testing Modular Database Services against Aiven PostgreSQL...")

    with next(get_db()) as db:
        # 1. Test City Service
        print("\n1. Testing City Service...")
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
        print(f"   [SUCCESS] City record: {city}")

        # 2. Test Category Seeding
        print("\n2. Testing Category Seeding Service...")
        categories = seed_default_categories(db)
        print(f"   [SUCCESS] Seeded {len(categories)} standard 15-minute city service categories.")

        # 3. Test Execution Creation
        print("\n3. Testing Execution Service...")
        execution = create_execution(db, city_id=city.id, speed_kmh=3.0)
        print(f"   [SUCCESS] Created Execution ID: {execution.id}")

        # 4. Test Bulk Nodes Saving
        print("\n4. Testing Bulk Nodes Service...")
        sample_nodes = [
            {"osm_id": 10001, "lat": -24.005, "lon": -46.405, "overall_index": 0.85, "overall_mean_time": 11.5},
            {"osm_id": 10002, "lat": -24.006, "lon": -46.406, "overall_index": 0.90, "overall_mean_time": 9.2},
        ]
        node_map = bulk_save_nodes(db, execution.id, sample_nodes)
        print(f"   [SUCCESS] Bulk saved nodes. Node OSM ID mapping: {node_map}")

        # 5. Test Bulk Services Saving
        print("\n5. Testing Bulk Services Saving...")
        pharmacy_category = categories[5]  # pharmacy
        sample_services = [
            {
                "category_id": pharmacy_category.id,
                "name": "Farmacia Central",
                "lat": -24.0051,
                "lon": -46.4051,
                "representative_node_id": node_map[10001],
            }
        ]
        services = bulk_save_services(db, execution.id, sample_services)
        print(f"   [SUCCESS] Bulk saved services: {services}")

        # 6. Test Node Reachabilities Saving
        print("\n6. Testing Node Reachabilities Saving...")
        sample_reachabilities = [
            {
                "node_id": node_map[10001],
                "category_id": pharmacy_category.id,
                "closest_service_id": services[0].id,
                "travel_time_minutes": 4.5,
                "within_threshold": True,
            }
        ]
        bulk_save_node_reachabilities(db, sample_reachabilities)
        print("   [SUCCESS] Bulk saved node reachability measurements.")

        # 7. Test City Indices Saving
        print("\n7. Testing City Indices Saving...")
        sample_indices = [
            {
                "category_id": pharmacy_category.id,
                "mean_travel_time_minutes": 4.5,
                "percentage_within_threshold": 100.0,
                "overall_index": 0.95,
            }
        ]
        save_city_indices(db, execution.id, sample_indices)
        indices = get_city_indices_for_execution(db, execution.id)
        print(f"   [SUCCESS] Saved and retrieved City Indices: {indices}")

        # 8. Complete Execution Status
        update_execution_status(db, execution.id, status="completed", execution_time_seconds=1.25)
        db.commit()
        print(f"\n[ALL TESTS PASSED SUCCESSFULLY] Execution #{execution.id} status updated to completed!")


if __name__ == "__main__":
    main()
