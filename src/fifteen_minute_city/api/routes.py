from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from fifteen_minute_city.api import service
from fifteen_minute_city.api.auth import require_api_key
from fifteen_minute_city.api.schemas import (
    CategoryResponse,
    CityResponse,
    DetailedResultResponse,
    ExecutionResponse,
    HistoryResponse,
    MetricHistoryResponse,
    MetricResponse,
    StrategyReportResponse,
)
from fifteen_minute_city.db.connection import get_db
from fifteen_minute_city.db.models.city import City
from fifteen_minute_city.db.models.execution import Execution

DbSession = Annotated[Session, Depends(get_db)]
StrategyName = Annotated[
    str,
    Path(description="Public strategy name: 'nodes' or 'population'"),
]

router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
)


def _city_or_404(db: Session, city_id: int) -> City:
    city = service.get_city(db, city_id)
    if city is None:
        raise HTTPException(status_code=404, detail="City not found")
    return city


def _latest_or_404(db: Session, city_id: int) -> Execution:
    _city_or_404(db, city_id)
    execution = service.latest_completed_execution(db, city_id)
    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="No completed execution found for this city",
        )
    return execution


def _internal_strategy_or_404(public_strategy: str) -> str:
    internal_strategy = service.resolve_strategy(public_strategy)
    if internal_strategy is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown strategy; use 'nodes' or 'population'",
        )
    return internal_strategy


def _report_or_404(
    db: Session,
    execution_id: int,
    public_strategy: str,
) -> dict:
    internal_strategy = _internal_strategy_or_404(public_strategy)
    report = service.build_strategy_report(db, execution_id, internal_strategy)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="The requested strategy is unavailable for this execution",
        )
    return report


def _metric_or_404(
    execution: Execution,
    public_strategy: str,
    report: dict,
    metric: str,
    *,
    category: str | None = None,
) -> dict:
    try:
        return service.build_metric_response(
            execution,
            public_strategy,
            report,
            metric,
            category=category,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown metric") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Category not found") from exc


@router.get("/version", tags=["system"])
def api_version() -> dict[str, str]:
    return {"name": "15minute-city-api", "version": "1.0.0"}


@router.get("/cities", response_model=list[CityResponse], tags=["cities"])
def cities(db: DbSession) -> list[City]:
    return service.list_public_cities(db)


@router.get("/cities/{city_id}", response_model=CityResponse, tags=["cities"])
def city(city_id: int, db: DbSession) -> City:
    return _city_or_404(db, city_id)


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    tags=["categories"],
)
def categories(db: DbSession):
    return service.list_public_categories(db)


@router.get(
    "/cities/{city_id}/executions",
    response_model=list[ExecutionResponse],
    tags=["executions"],
)
def executions(
    city_id: int,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    _city_or_404(db, city_id)
    return [
        service.serialize_execution(execution)
        for execution in service.list_completed_executions(
            db,
            city_id,
            limit=limit,
            offset=offset,
        )
    ]


@router.get(
    "/executions/{execution_id}",
    response_model=DetailedResultResponse,
    tags=["results"],
)
def execution_result(execution_id: int, db: DbSession) -> dict:
    execution = service.get_completed_execution(db, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Completed execution not found")
    return service.build_detailed_result(db, execution)


@router.get(
    "/cities/{city_id}/latest",
    response_model=DetailedResultResponse,
    tags=["results"],
)
def latest_result(city_id: int, db: DbSession) -> dict:
    execution = _latest_or_404(db, city_id)
    return service.build_detailed_result(db, execution)


@router.get(
    "/cities/{city_id}/latest/{strategy}",
    response_model=StrategyReportResponse,
    tags=["results"],
)
def latest_strategy(city_id: int, strategy: StrategyName, db: DbSession) -> dict:
    execution = _latest_or_404(db, city_id)
    return _report_or_404(db, execution.id, strategy)


@router.get(
    "/cities/{city_id}/latest/{strategy}/{metric}",
    response_model=MetricResponse,
    tags=["metrics"],
)
def latest_overall_metric(
    city_id: int,
    strategy: StrategyName,
    metric: str,
    db: DbSession,
) -> dict:
    execution = _latest_or_404(db, city_id)
    report = _report_or_404(db, execution.id, strategy)
    return _metric_or_404(execution, strategy, report, metric)


@router.get(
    "/cities/{city_id}/latest/{strategy}/{category}/{metric}",
    response_model=MetricResponse,
    tags=["metrics"],
)
def latest_category_metric(
    city_id: int,
    strategy: StrategyName,
    category: str,
    metric: str,
    db: DbSession,
) -> dict:
    execution = _latest_or_404(db, city_id)
    report = _report_or_404(db, execution.id, strategy)
    return _metric_or_404(
        execution,
        strategy,
        report,
        metric,
        category=category,
    )


@router.get(
    "/cities/{city_id}/history",
    response_model=HistoryResponse,
    tags=["history"],
)
def history(
    city_id: int,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    city = _city_or_404(db, city_id)
    completed = service.list_completed_executions(
        db,
        city_id,
        limit=limit,
        offset=offset,
    )
    return {
        "city": city,
        "count": len(completed),
        "results": [
            service.build_detailed_result(db, execution) for execution in completed
        ],
    }


@router.get(
    "/cities/{city_id}/history/{strategy}/{metric}",
    response_model=MetricHistoryResponse,
    tags=["history"],
)
def overall_metric_history(
    city_id: int,
    strategy: StrategyName,
    metric: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    return _metric_history(
        city_id,
        strategy,
        metric,
        db,
        category=None,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/cities/{city_id}/history/{strategy}/{category}/{metric}",
    response_model=MetricHistoryResponse,
    tags=["history"],
)
def category_metric_history(
    city_id: int,
    strategy: StrategyName,
    category: str,
    metric: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    return _metric_history(
        city_id,
        strategy,
        metric,
        db,
        category=category,
        limit=limit,
        offset=offset,
    )


def _metric_history(
    city_id: int,
    strategy: str,
    metric: str,
    db: Session,
    *,
    category: str | None,
    limit: int,
    offset: int,
) -> dict:
    city = _city_or_404(db, city_id)
    internal_strategy = _internal_strategy_or_404(strategy)
    valid_metrics = (
        service.OVERALL_METRICS if category is None else service.CATEGORY_METRICS
    )
    if metric not in valid_metrics:
        raise HTTPException(status_code=404, detail="Unknown metric")
    if category is not None and not any(
        registered.code == category for registered in service.list_public_categories(db)
    ):
        raise HTTPException(status_code=404, detail="Category not found")

    completed = service.list_completed_executions(
        db,
        city_id,
        limit=limit,
        offset=offset,
    )
    observations = []
    for execution in completed:
        report = service.build_strategy_report(db, execution.id, internal_strategy)
        if report is None or (
            category is not None and category not in report["categories"]
        ):
            continue
        observations.append(
            _metric_or_404(
                execution,
                strategy,
                report,
                metric,
                category=category,
            )
        )
    return {
        "city": city,
        "strategy": strategy,
        "category": category,
        "metric": metric,
        "count": len(observations),
        "results": observations,
    }
