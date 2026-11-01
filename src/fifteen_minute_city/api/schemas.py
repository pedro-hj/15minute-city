from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    display_name: str
    moreno_pillar: str


class ExecutionResponse(BaseModel):
    id: int
    city_id: int
    processed_at: datetime.datetime
    status: str
    speed_kmh: float
    threshold_minutes: float
    network_type: str
    execution_time_seconds: float | None


class CategoryMetricsResponse(BaseModel):
    category: str
    total_weight: float
    reachable_weight: float
    within_threshold_weight: float
    unreachable_weight: float
    coverage_percentage: float
    unreachable_percentage: float
    mean_travel_time_minutes: float | None
    median_travel_time_minutes: float | None


class StrategyReportResponse(BaseModel):
    origin_strategy: str
    weight_unit: str
    threshold_minutes: float
    total_weight: float
    categories: dict[str, CategoryMetricsResponse]
    overall_coverage_percentage: float
    overall_unreachable_percentage: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComparisonResponse(BaseModel):
    calculation: str
    unit: str
    category_coverage_delta: dict[str, float]
    category_unreachable_delta: dict[str, float]
    overall_coverage_delta: float
    overall_unreachable_delta: float


class DetailedResultResponse(BaseModel):
    execution: ExecutionResponse
    node_report: StrategyReportResponse | None
    population_report: StrategyReportResponse | None
    comparison: ComparisonResponse | None


class MetricResponse(BaseModel):
    city_id: int
    execution_id: int
    processed_at: datetime.datetime
    strategy: str
    category: str | None
    metric: str
    value: float | None
    unit: str
    threshold_minutes: float


class HistoryResponse(BaseModel):
    city: CityResponse
    count: int
    results: list[DetailedResultResponse]


class MetricHistoryResponse(BaseModel):
    city: CityResponse
    strategy: str
    category: str | None
    metric: str
    count: int
    results: list[MetricResponse]


class SimulationServiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    category: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    services: list[SimulationServiceInput] = Field(min_length=1, max_length=200)


class SimulationCategoryMetrics(BaseModel):
    coverage_percentage: float
    unreachable_percentage: float
    mean_travel_time_minutes: float | None
    median_travel_time_minutes: float | None


class SimulationCategoryComparison(BaseModel):
    before: SimulationCategoryMetrics
    after: SimulationCategoryMetrics
    coverage_delta_percentage_points: float


class SimulationCategoryResults(BaseModel):
    population: SimulationCategoryComparison
    nodes: SimulationCategoryComparison


class SimulationPlacedService(BaseModel):
    category: str
    name: str | None
    longitude: float
    latitude: float
    graph_node_index: int
    snap_distance_m: float


class SimulationResponse(BaseModel):
    execution_id: int
    added_services: list[SimulationPlacedService]
    results: dict[str, SimulationCategoryResults]
    processing_time_ms: float
