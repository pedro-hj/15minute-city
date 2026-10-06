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
