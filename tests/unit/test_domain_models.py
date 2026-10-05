import pytest

from fifteen_minute_city.domain.models import (
    AccessibilityComparison,
    AccessibilityReport,
    CategoryAccessibility,
    Origin,
    OriginAccessibility,
    OriginSet,
)


def test_origin_represents_weight_associated_with_graph_node() -> None:
    origin = Origin(origin_id="cell:25", node_id=101, weight=350)

    assert origin.origin_id == "cell:25"
    assert origin.node_id == 101
    assert origin.weight == 350


@pytest.mark.parametrize(
    ("origin_id", "weight"),
    [
        ("", 100),
        ("cell:25", 0),
        ("cell:25", -1),
        ("cell:25", float("inf")),
        ("cell:25", float("nan")),
    ],
)
def test_origin_rejects_invalid_identity_or_weight(
    origin_id: str, weight: float
) -> None:
    with pytest.raises(ValueError):
        Origin(origin_id=origin_id, node_id=101, weight=weight)


def test_origin_set_calculates_total_weight() -> None:
    origins = OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=(
            Origin(origin_id="cell:1", node_id=101, weight=350),
            Origin(origin_id="cell:2", node_id=102, weight=150),
        ),
        source="population.zip",
    )

    assert origins.total_weight == 500


def test_origin_set_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="origin IDs must be unique"):
        OriginSet(
            strategy="population_grid",
            weight_unit="population",
            origins=(
                Origin(origin_id="cell:1", node_id=101, weight=350),
                Origin(origin_id="cell:1", node_id=102, weight=150),
            ),
        )


def test_origin_accessibility_derives_reachability_and_threshold() -> None:
    result = OriginAccessibility(
        origin=Origin(origin_id="cell:25", node_id=101, weight=350),
        travel_time_minutes=8.4,
        nearest_service_node_id=900,
    )

    assert result.origin_id == "cell:25"
    assert result.node_id == 101
    assert result.weight == 350
    assert result.reachable is True
    assert result.is_within(15) is True
    assert result.is_within(5) is False


def test_unreachable_origin_has_no_time_or_service_node() -> None:
    result = OriginAccessibility(
        origin=Origin(origin_id="cell:25", node_id=101, weight=350),
        travel_time_minutes=None,
        nearest_service_node_id=None,
    )

    assert result.reachable is False
    assert result.is_within(15) is False


def test_origin_accessibility_rejects_contradictory_raw_data() -> None:
    with pytest.raises(
        ValueError,
        match="travel time and nearest service node must both be present or absent",
    ):
        OriginAccessibility(
            origin=Origin(origin_id="cell:25", node_id=101, weight=350),
            travel_time_minutes=8.4,
            nearest_service_node_id=None,
        )


def test_category_accessibility_derives_percentages_and_score() -> None:
    result = CategoryAccessibility(
        category="health",
        threshold_minutes=15,
        total_weight=1_000,
        reachable_weight=900,
        within_threshold_weight=750,
        mean_travel_time_minutes=9.2,
        median_travel_time_minutes=8.5,
    )

    assert result.unreachable_weight == 100
    assert result.coverage_percentage == 75
    assert result.unreachable_percentage == 10
    assert result.score == 75


def test_category_accessibility_rejects_inconsistent_weights() -> None:
    with pytest.raises(
        ValueError,
        match="within-threshold weight must not exceed reachable weight",
    ):
        CategoryAccessibility(
            category="health",
            threshold_minutes=15,
            total_weight=1_000,
            reachable_weight=700,
            within_threshold_weight=800,
            mean_travel_time_minutes=9.2,
            median_travel_time_minutes=8.5,
        )


def test_accessibility_report_derives_overall_metrics_and_serializes() -> None:
    health = CategoryAccessibility(
        category="health",
        threshold_minutes=15,
        total_weight=1_000,
        reachable_weight=900,
        within_threshold_weight=750,
        mean_travel_time_minutes=9.2,
        median_travel_time_minutes=8.5,
    )
    report = AccessibilityReport(
        origin_strategy="population_grid",
        weight_unit="population",
        threshold_minutes=15,
        total_weight=1_000,
        categories={"health": health},
        overall_within_threshold_weight=750,
        overall_unreachable_weight=100,
    )

    assert report.overall_coverage_percentage == 75
    assert report.overall_unreachable_percentage == 10
    assert report.overall_score == 75
    assert report.to_dict()["categories"]["health"]["score"] == 75


def test_accessibility_report_rejects_mismatched_category_key() -> None:
    health = CategoryAccessibility(
        category="health",
        threshold_minutes=15,
        total_weight=1_000,
        reachable_weight=900,
        within_threshold_weight=750,
        mean_travel_time_minutes=9.2,
        median_travel_time_minutes=8.5,
    )

    with pytest.raises(ValueError, match="category key must match"):
        AccessibilityReport(
            origin_strategy="population_grid",
            weight_unit="population",
            threshold_minutes=15,
            total_weight=1_000,
            categories={"education": health},
            overall_within_threshold_weight=750,
            overall_unreachable_weight=100,
        )


def _report(*, strategy: str, coverage_weight: float) -> AccessibilityReport:
    category = CategoryAccessibility(
        category="health",
        threshold_minutes=15,
        total_weight=1_000,
        reachable_weight=900,
        within_threshold_weight=coverage_weight,
        mean_travel_time_minutes=9.2,
        median_travel_time_minutes=8.5,
    )
    return AccessibilityReport(
        origin_strategy=strategy,
        weight_unit="population" if strategy == "population_grid" else "nodes",
        threshold_minutes=15,
        total_weight=1_000,
        categories={"health": category},
        overall_within_threshold_weight=coverage_weight,
        overall_unreachable_weight=100,
    )


def test_accessibility_comparison_derives_deltas() -> None:
    comparison = AccessibilityComparison(
        population_report=_report(
            strategy="population_grid",
            coverage_weight=750,
        ),
        node_report=_report(
            strategy="graph_nodes",
            coverage_weight=600,
        ),
    )

    assert comparison.category_coverage_delta == {"health": 15}
    assert comparison.category_unreachable_delta == {"health": 0}
    assert comparison.overall_coverage_delta == 15
    assert comparison.overall_unreachable_delta == 0
    assert comparison.to_dict()["overall_coverage_delta"] == 15


def test_accessibility_comparison_requires_same_categories() -> None:
    population_report = _report(
        strategy="population_grid",
        coverage_weight=750,
    )
    node_report = _report(
        strategy="graph_nodes",
        coverage_weight=600,
    )
    health = node_report.categories["health"]
    education = CategoryAccessibility(
        category="education",
        threshold_minutes=health.threshold_minutes,
        total_weight=health.total_weight,
        reachable_weight=health.reachable_weight,
        within_threshold_weight=health.within_threshold_weight,
        mean_travel_time_minutes=health.mean_travel_time_minutes,
        median_travel_time_minutes=health.median_travel_time_minutes,
    )
    mismatched_node_report = AccessibilityReport(
        origin_strategy=node_report.origin_strategy,
        weight_unit=node_report.weight_unit,
        threshold_minutes=15,
        total_weight=1_000,
        categories={"education": education},
        overall_within_threshold_weight=600,
        overall_unreachable_weight=100,
    )

    with pytest.raises(ValueError, match="same service categories"):
        AccessibilityComparison(population_report, mismatched_node_report)
