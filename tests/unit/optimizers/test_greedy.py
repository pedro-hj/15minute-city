import networkx as nx
import pytest

from fifteen_minute_city.application.optimizers import create_optimizer
from fifteen_minute_city.application.optimizers.greedy import GreedyLocationOptimizer
from fifteen_minute_city.application.server_simulation import decode_package
from fifteen_minute_city.application.simulation_package import build_package


def create_mock_bundle():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"

    graph.add_node(0, x=0.0, y=0.0)
    graph.add_node(1, x=0.005, y=0.0)
    graph.add_node(2, x=0.010, y=0.0)

    graph.add_edge(0, 1, length=1000)
    graph.add_edge(1, 0, length=1000)
    graph.add_edge(1, 2, length=1000)
    graph.add_edge(2, 1, length=1000)

    raw_package = build_package(
        graph,
        execution_id=99,
        speed_kmh=3.0,
        threshold_minutes=15.0,
        categories=["health", "education"],
        population_by_osm={0: 100.0, 1: 20.0, 2: 500.0},
        baseline_minutes={
            (0, "health"): 0.0,
            (0, "education"): 30.0,
            (1, "health"): 20.0,
            (1, "education"): 30.0,
            (2, "health"): 40.0,
            (2, "education"): 30.0,
        },
        pbf_checksum="mock_pbf_hash_" + "0" * 50,
        graph_cache_key="mock_cache_key_" + "0" * 9,
    )
    return decode_package(raw_package)


def test_greedy_selects_highest_population_unserved_node():
    bundle = create_mock_bundle()
    optimizer = create_optimizer()

    assert isinstance(optimizer, GreedyLocationOptimizer)
    result = optimizer.optimize(bundle, category="health", k=1)

    assert result.strategy == "greedy"
    assert result.category == "health"
    assert len(result.locations) == 1

    best_location = result.locations[0]
    assert best_location.node_id == 2
    assert best_location.rank == 1
    assert best_location.marginal_population == 500.0

    assert result.baseline_coverage_percentage == pytest.approx(16.129, abs=0.01)
    assert result.simulated_coverage_percentage == pytest.approx(96.774, abs=0.01)
    assert result.coverage_delta_percentage_points == pytest.approx(80.645, abs=0.01)


def test_greedy_validates_invalid_inputs():
    bundle = create_mock_bundle()
    optimizer = GreedyLocationOptimizer()

    with pytest.raises(ValueError, match="k must be at least 1"):
        optimizer.optimize(bundle, category="health", k=0)

    with pytest.raises(ValueError, match="Category 'culture' not found"):
        optimizer.optimize(bundle, category="culture", k=1)


def test_optimizer_factory_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="Unknown optimization strategy"):
        create_optimizer("unknown")


def test_greedy_considers_unpopulated_transit_nodes():
    graph = nx.MultiDiGraph()
    for node in range(3):
        graph.add_node(node, x=node * 0.001, y=0.0)
    for origin, target in ((0, 1), (1, 0), (1, 2), (2, 1)):
        graph.add_edge(origin, target, length=250)

    bundle = decode_package(
        build_package(
            graph,
            execution_id=1,
            speed_kmh=3.0,
            threshold_minutes=5.0,
            categories=["health"],
            population_by_osm={0: 10.0, 1: 0.0, 2: 10.0},
            baseline_minutes={(node, "health"): None for node in range(3)},
            pbf_checksum="test",
            graph_cache_key="test",
        )
    )

    result = GreedyLocationOptimizer().optimize(bundle, "health", k=2)

    assert len(result.locations) == 1
    assert result.locations[0].node_id == 1
    assert result.locations[0].marginal_population == 20.0
    assert result.simulated_coverage_percentage == 100.0


@pytest.mark.parametrize("candidate", [-1, 3, True])
def test_greedy_rejects_invalid_candidate_indices(candidate):
    bundle = create_mock_bundle()

    with pytest.raises(ValueError, match="candidate_pool"):
        GreedyLocationOptimizer().optimize(bundle, "health", candidate_pool=[candidate])


@pytest.mark.parametrize("threshold", [0.0, -1.0, float("nan"), float("inf"), 1e308])
def test_greedy_rejects_invalid_thresholds(threshold):
    bundle = create_mock_bundle()

    with pytest.raises(ValueError, match="threshold_minutes"):
        GreedyLocationOptimizer().optimize(
            bundle, "health", threshold_minutes=threshold
        )


@pytest.mark.parametrize("distance", [-1.0, float("nan"), float("inf")])
def test_greedy_rejects_invalid_minimum_distances(distance):
    bundle = create_mock_bundle()

    with pytest.raises(ValueError, match="min_distance_m"):
        GreedyLocationOptimizer().optimize(bundle, "health", min_distance_m=distance)
