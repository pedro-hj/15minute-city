import networkx as nx
import pytest

from fifteen_minute_city.application.optimizers.greedy import GreedyLocationOptimizer
from fifteen_minute_city.application.server_simulation import decode_package
from fifteen_minute_city.application.simulation_package import build_package


def create_mock_bundle():
    """Cria um SimulationBundle sintético para testes unitários determinísticos."""
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"

    # 3 nós em linha: 0 (Norte), 1 (Centro), 2 (Sul)
    graph.add_node(0, x=0.0, y=0.0)
    graph.add_node(1, x=0.005, y=0.0)
    graph.add_node(2, x=0.010, y=0.0)

    # Cada aresta tem 1000m (com velocidade de 3 km/h = 20 min de caminhada)
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
            (0, "health"): 0.0,  # Já atendido
            (0, "education"): 30.0,
            (1, "health"): 20.0,  # Desatendido
            (1, "education"): 30.0,
            (2, "health"): 40.0,  # Desatendido com grande população
            (2, "education"): 30.0,
        },
        pbf_checksum="mock_pbf_hash_" + "0" * 50,
        graph_cache_key="mock_cache_key_" + "0" * 9,
    )
    return decode_package(raw_package)


def test_greedy_selects_highest_population_unserved_node():
    bundle = create_mock_bundle()
    optimizer = GreedyLocationOptimizer()

    result = optimizer.optimize(bundle, category="health", k=1)

    assert result.strategy == "greedy"
    assert result.category == "health"
    assert len(result.locations) == 1

    best_location = result.locations[0]
    # O nó 2 (com 500 habitantes) DEVE ser o escolhido
    assert best_location.node_id == 2
    assert best_location.rank == 1
    assert best_location.marginal_population == 500.0

    # Cobertura passou de ~16.1% para ~96.8%
    assert result.baseline_coverage_percentage == pytest.approx(16.129, abs=0.01)
    assert result.simulated_coverage_percentage == pytest.approx(96.774, abs=0.01)
    assert result.coverage_delta_percentage_points == pytest.approx(80.645, abs=0.01)


def test_greedy_validates_invalid_inputs():
    bundle = create_mock_bundle()
    optimizer = GreedyLocationOptimizer()

    # k deve ser >= 1
    with pytest.raises(ValueError, match="k must be at least 1"):
        optimizer.optimize(bundle, category="health", k=0)

    # Categoria inexistente deve falhar com erro claro
    with pytest.raises(ValueError, match="Category 'culture' not found"):
        optimizer.optimize(bundle, category="culture", k=1)
