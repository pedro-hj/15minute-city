import datetime
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fifteen_minute_city.db.base import Base


class Execution(Base):
    """
    Represents a specific run of the reachability algorithm for a city.
    
    Isolates computational results per date and speed parameter, enabling historical tracking.
    """

    __tablename__ = "execution"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Unique primary key identifier for the execution"
    )
    city_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("city.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key referencing the analyzed city",
    )
    processed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when the execution was initiated",
    )
    speed_kmh: Mapped[float] = mapped_column(
        Float, nullable=False, default=3.0, comment="Walking/transport speed parameter in km/h"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="processing",
        index=True,
        comment="Execution status (e.g., 'processing', 'completed', 'error')",
    )
    execution_time_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Total execution processing duration in seconds"
    )

    # Relationships
    city: Mapped["City"] = relationship("City", back_populates="executions")
    nodes: Mapped[list["Node"]] = relationship(
        "Node", back_populates="execution", cascade="all, delete-orphan"
    )
    services: Mapped[list["Service"]] = relationship(
        "Service", back_populates="execution", cascade="all, delete-orphan"
    )
    city_indices: Mapped[list["CityIndex"]] = relationship(
        "CityIndex", back_populates="execution", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Execution(id={self.id}, city_id={self.city_id}, status='{self.status}')>"
