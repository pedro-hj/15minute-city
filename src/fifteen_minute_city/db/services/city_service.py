import json
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import shape

from fifteen_minute_city.db.models.city import City


def get_city_by_id(db: Session, city_id: int) -> Optional[City]:
    """Retrieve a City by its unique primary key ID."""
    return db.scalar(select(City).where(City.id == city_id))


def get_city_by_name_and_country(db: Session, name: str, country: str) -> Optional[City]:
    """Retrieve a City by its exact name and country."""
    return db.scalar(
        select(City).where(City.name == name, City.country == country)
    )


def list_cities(db: Session) -> List[City]:
    """Retrieve all registered cities in the database."""
    return list(db.scalars(select(City).order_by(City.name)).all())


def get_or_create_city(
    db: Session,
    name: str,
    country: str,
    geom_boundary_geojson: Optional[dict] = None,
) -> City:
    """
    Retrieve an existing City or create a new one if it does not exist.

    :param db: SQLAlchemy Session.
    :param name: Name of the city (e.g., 'Praia Grande', 'Paris').
    :param country: Country name (e.g., 'Brazil', 'France').
    :param geom_boundary_geojson: Optional GeoJSON dictionary representing the polygon boundary.
    :return: City instance.
    """
    city = get_city_by_name_and_country(db, name, country)
    if city:
        return city

    # Convert GeoJSON boundary dictionary to WKB/Geometry if provided
    geom = None
    if geom_boundary_geojson:
        shapely_geom = shape(geom_boundary_geojson)
        geom = from_shape(shapely_geom, srid=4326)

    city = City(
        name=name,
        country=country,
        geom_boundary=geom,
    )
    db.add(city)
    db.commit()
    db.refresh(city)
    return city
