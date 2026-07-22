from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from fifteen_minute_city.db.base import Base


class City(Base):
    """
    Represents a city or delimited urban region analyzed by the system.
    
    Serves as an entry point for urban mobility queries and holds historical algorithm executions.
    """

    __tablename__ = "city"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Unique primary key identifier for the city"
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="City name (e.g., 'Paris', 'Praia Grande')"
    )
    country: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Country name to which the city belongs"
    )
    geom_boundary = mapped_column(
        Geometry("POLYGON", srid=4326),
        nullable=True,
        comment="Geographic boundary polygon of the city extracted from OpenStreetMap (EPSG:4326)",
    )

    # Relationships
    executions: Mapped[list["Execution"]] = relationship(
        "Execution", back_populates="city", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<City(id={self.id}, name='{self.name}', country='{self.country}')>"
