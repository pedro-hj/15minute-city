from typing import Optional, Dict, Any
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from geoalchemy2.shape import to_shape
import shapely.geometry

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

    @property
    def geojson_boundary(self) -> Optional[Dict[str, Any]]:
        """Convert spatial WKBElement boundary geometry into a JSON-serializable GeoJSON dict."""
        if self.geom_boundary is None:
            return None
        shapely_obj = to_shape(self.geom_boundary)
        return shapely.geometry.mapping(shapely_obj)

    def to_dict(self) -> Dict[str, Any]:
        """Convert City model instance into a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "country": self.country,
            "geom_boundary": self.geojson_boundary,
        }

    def __repr__(self) -> str:
        return f"<City(id={self.id}, name='{self.name}', country='{self.country}')>"
