import json

import geopandas as gpd
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from fifteen_minute_city.db.models.city import City


def get_city_by_id(db: Session, city_id: int) -> City | None:
    """Retrieve a City by its unique primary key ID."""
    return db.scalar(select(City).where(City.id == city_id))


def get_city_by_name_and_country(db: Session, name: str, country: str) -> City | None:
    """Retrieve a City by its exact name and country."""
    return db.scalar(
        select(City).where(City.name == name, City.country == country)
    )


def list_cities(db: Session) -> list[City]:
    """Retrieve all registered cities in the database."""
    return list(db.scalars(select(City).order_by(City.name)).all())


def get_or_create_city(
    db: Session,
    name: str,
    country: str,
    geom_boundary_geojson: dict | None = None,
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
        if geom_boundary_geojson and city.geom_boundary is None:
            shapely_geom = shape(geom_boundary_geojson)
            city.geom_boundary = from_shape(shapely_geom, srid=4326)
            db.commit()
            db.refresh(city)
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


def get_city_boundary_gdf(db: Session, name: str, country: str) -> gpd.GeoDataFrame | None:
    """
    Retrieve the geographic boundary of a city as a GeoDataFrame if present in database.

    :param db: SQLAlchemy Session.
    :param name: Name of the city.
    :param country: Country name.
    :return: GeoPandas GeoDataFrame with 'geometry' column, or None.
    """
    city = get_city_by_name_and_country(db, name, country)
    if city and city.geom_boundary is not None:
        shapely_obj = to_shape(city.geom_boundary)
        return gpd.GeoDataFrame(
            {"geometry": [shapely_obj], "name": [name], "country": [country]},
            crs="EPSG:4326",
        )
    return None


def save_city_boundary_from_gdf(
    db: Session, name: str, country: str, gdf: gpd.GeoDataFrame
) -> City:
    """
    Save or update the city boundary polygon from a GeoPandas GeoDataFrame.

    :param db: SQLAlchemy Session.
    :param name: Name of the city.
    :param country: Country name.
    :param gdf: GeoPandas GeoDataFrame containing the city boundary geometry.
    :return: Updated or created City instance.
    """
    if gdf.empty or "geometry" not in gdf.columns:
        return get_or_create_city(db, name=name, country=country)

    geom_obj = gdf.geometry.iloc[0]
    geojson_dict = json.loads(gpd.GeoSeries([geom_obj]).to_json())
    features = geojson_dict.get("features", [])
    geom_data = features[0].get("geometry") if features else None

    return get_or_create_city(db, name=name, country=country, geom_boundary_geojson=geom_data)
