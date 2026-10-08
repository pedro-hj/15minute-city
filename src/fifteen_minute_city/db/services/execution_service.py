from sqlalchemy import select
from sqlalchemy.orm import Session

from fifteen_minute_city.db.models.execution import Execution


def create_execution(
    db: Session,
    city_id: int,
    speed_kmh: float = 3.0,
    status: str = "processing",
    threshold_minutes: float = 15.0,
    network_type: str = "walk",
    pbf_source: str | None = None,
    pbf_checksum: str | None = None,
    population_source: str | None = None,
    population_column: str | None = None,
    analysis_metadata: dict | None = None,
) -> Execution:
    """
    Create and persist a new execution record for a city.

    :param db: SQLAlchemy Session.
    :param city_id: Primary key ID of the target city.
    :param speed_kmh: Walking speed parameter adopted for the run (default: 3.0 km/h).
    :param status: Initial execution status (default: 'processing').
    :return: Created Execution instance.
    """
    execution = Execution(
        city_id=city_id,
        speed_kmh=speed_kmh,
        status=status,
        threshold_minutes=threshold_minutes,
        network_type=network_type,
        pbf_source=pbf_source,
        pbf_checksum=pbf_checksum,
        population_source=population_source,
        population_column=population_column,
        analysis_metadata=analysis_metadata,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def get_execution_by_id(db: Session, execution_id: int) -> Execution | None:
    """Retrieve an Execution by its unique primary key ID."""
    return db.scalar(select(Execution).where(Execution.id == execution_id))


def update_execution_metadata(
    db: Session,
    execution_id: int,
    *,
    pbf_checksum: str | None = None,
    population_source: str | None = None,
    population_column: str | None = None,
    analysis_metadata: dict | None = None,
) -> Execution:
    """Update reproducibility metadata as external artifacts become available."""
    execution = get_execution_by_id(db, execution_id)
    if execution is None:
        raise ValueError(f"Execution with ID {execution_id} not found.")
    if pbf_checksum is not None:
        execution.pbf_checksum = pbf_checksum
    if population_source is not None:
        execution.population_source = population_source
    if population_column is not None:
        execution.population_column = population_column
    if analysis_metadata is not None:
        execution.analysis_metadata = analysis_metadata
    db.flush()
    return execution


def list_executions_for_city(db: Session, city_id: int) -> list[Execution]:
    """Retrieve all execution runs associated with a specific city ordered chronologically."""
    return list(
        db.scalars(
            select(Execution)
            .where(Execution.city_id == city_id)
            .order_by(Execution.processed_at.desc())
        ).all()
    )


def update_execution_status(
    db: Session,
    execution_id: int,
    status: str,
    execution_time_seconds: float | None = None,
    error_message: str | None = None,
) -> Execution:
    """
    Update the status and optional runtime duration of an execution.

    :param db: SQLAlchemy Session.
    :param execution_id: ID of the execution.
    :param status: New status (e.g., 'completed', 'error').
    :param execution_time_seconds: Total processing time in seconds.
    :return: Updated Execution instance.
    """
    execution = get_execution_by_id(db, execution_id)
    if not execution:
        raise ValueError(f"Execution with ID {execution_id} not found.")

    execution.status = status
    if execution_time_seconds is not None:
        execution.execution_time_seconds = execution_time_seconds
    execution.error_message = error_message

    db.commit()
    db.refresh(execution)
    return execution
