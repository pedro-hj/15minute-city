from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.orm import Session

from fifteen_minute_city.db.models.execution import Execution


def create_execution(
    db: Session,
    city_id: int,
    speed_kmh: float = 3.0,
    status: str = "processing",
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
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def get_execution_by_id(db: Session, execution_id: int) -> Optional[Execution]:
    """Retrieve an Execution by its unique primary key ID."""
    return db.scalar(select(Execution).where(Execution.id == execution_id))


def list_executions_for_city(db: Session, city_id: int) -> List[Execution]:
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
    execution_time_seconds: Optional[float] = None,
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

    db.commit()
    db.refresh(execution)
    return execution
