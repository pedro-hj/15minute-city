"""
Integration test demonstrating the clean 3-method interface of AlgorithmPipeline for the algorithm developer.
"""

import time
from fifteen_minute_city.db.pipelines import AlgorithmPipeline


def main():
    print("Testing AlgorithmPipeline Facade for Algorithm Developer...")
    start_time = time.time()

    # 1. Instantiate Pipeline Facade
    pipeline = AlgorithmPipeline()

    # 2. Step 1: Prepare Execution (Beginning of algorithm run)
    print("\nStep 1: Algorithm calls pipeline.prepare_execution(...)")
    ctx = pipeline.prepare_execution(
        city_name="Paris",
        country="France",
        speed_kmh=3.0,
    )

    print(f"   -> Created Execution Run ID: {ctx.execution_id}")
    print(f"   -> City: {ctx.city_name}, {ctx.country}")
    print(f"   -> Configured Categories for OSMnx: {[cat.code for cat in ctx.categories]}")

    # 3. Step 2: Algorithm runs OSMnx / Dijkstra computation (Simulated)
    print("\nStep 2: Algorithm performs spatial computations (OSMnx / Dijkstra)...")
    time.sleep(0.5)

    # Simulated computed data from algorithm
    sample_nodes = [
        {"osm_id": 99001, "lat": 48.8566, "lon": 2.3522, "overall_index": 0.92, "overall_mean_time": 8.5},
        {"osm_id": 99002, "lat": 48.8567, "lon": 2.3523, "overall_index": 0.88, "overall_mean_time": 10.1},
    ]

    sample_services = [
        {
            "category_id": ctx.categories[0].id,  # bus_station
            "name": "Gare de Lyon Bus Stop",
            "lat": 48.85665,
            "lon": 2.35225,
            "osm_node_id": 99001,
        }
    ]

    sample_reachabilities = [
        {
            "osm_node_id": 99001,
            "category_id": ctx.categories[0].id,
            "service_index": 0,
            "travel_time_minutes": 3.2,
            "within_threshold": True,
        }
    ]

    sample_city_indices = [
        {
            "category_id": ctx.categories[0].id,
            "mean_travel_time_minutes": 3.2,
            "percentage_within_threshold": 100.0,
            "overall_index": 0.96,
        }
    ]

    runtime_seconds = round(time.time() - start_time, 2)

    # 4. Step 3: Save Execution Results (End of algorithm run)
    print("\nStep 3: Algorithm calls pipeline.save_execution_results(...)")
    pipeline.save_execution_results(
        execution_id=ctx.execution_id,
        nodes_data=sample_nodes,
        services_data=sample_services,
        reachabilities_data=sample_reachabilities,
        city_indices_data=sample_city_indices,
        processing_time_seconds=runtime_seconds,
    )

    print(f"\n[PIPELINE TEST PASSED] Successfully completed execution #{ctx.execution_id} in {runtime_seconds}s!")


if __name__ == "__main__":
    main()
