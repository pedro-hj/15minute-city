"""Resolve which IBGE population ZIP tiles intersect a municipality.

Uses dataset metadata rather than inferring geography from grade_idXX names.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pyogrio
from pyproj import CRS, Transformer
from shapely.geometry import box


@dataclass(frozen=True)
class GridTile:
    path: Path
    bbox_wgs84: tuple[float, float, float, float]
    size: int
    mtime_ns: int


def _describe(path: Path) -> GridTile:
    info = pyogrio.read_info(f"zip://{path}")
    fields = set(info["fields"])
    missing = {"TOTAL", "ID_UNICO"} - fields
    if missing:
        raise ValueError(f"{path.name} is missing IBGE fields: {sorted(missing)}")
    if not info.get("crs"):
        raise ValueError(f"{path.name} has no coordinate reference system")
    extent = info.get("total_bounds")
    if extent is None:
        raise ValueError(f"{path.name} has no spatial extent")
    converter = Transformer.from_crs(
        CRS.from_user_input(info["crs"]), "EPSG:4326", always_xy=True
    )
    bounds = converter.transform_bounds(*[float(x) for x in extent], densify_pts=21)
    stat = path.stat()
    return GridTile(
        path=path,
        bbox_wgs84=tuple(bounds),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def grid_catalog(
    input_dir: Path,
    cache_dir: Path,
) -> list[GridTile]:
    """Index tiles once and refresh when any input ZIP changes."""
    input_dir = input_dir.expanduser().resolve()
    cache_dir = cache_dir.expanduser().resolve()
    files = sorted(input_dir.glob("grade_id*.zip"))
    if not files:
        raise FileNotFoundError(f"No grade_id*.zip population tiles in {input_dir}")

    manifest = [
        {
            "name": item.name,
            "size": item.stat().st_size,
            "mtime_ns": item.stat().st_mtime_ns,
        }
        for item in files
    ]
    catalog_path = cache_dir / "population-grids.json"
    if catalog_path.is_file():
        try:
            cached = json.loads(catalog_path.read_text(encoding="utf-8"))
            if cached.get("version") == 1 and cached.get("manifest") == manifest:
                return [
                    GridTile(
                        path=input_dir / item["name"],
                        bbox_wgs84=tuple(item["bbox"]),
                        size=item["size"],
                        mtime_ns=item["mtime_ns"],
                    )
                    for item in cached["tiles"]
                ]
        except (ValueError, KeyError, TypeError, OSError):
            pass

    tiles = [_describe(path) for path in files]
    cache_dir.mkdir(parents=True, exist_ok=True)
    document = {
        "version": 1,
        "manifest": manifest,
        "tiles": [
            {
                "name": tile.path.name,
                "bbox": list(tile.bbox_wgs84),
                "size": tile.size,
                "mtime_ns": tile.mtime_ns,
            }
            for tile in tiles
        ],
    }
    temp = catalog_path.with_name(f".{catalog_path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(document, indent=2), encoding="utf-8")
        os.replace(temp, catalog_path)
    finally:
        temp.unlink(missing_ok=True)
    return tiles


def select_population_grids(
    boundary: gpd.GeoDataFrame,
    *,
    input_dir: Path,
    cache_dir: Path,
) -> list[Path]:
    """Return all intersecting candidate tiles, including boundary-crossing cases."""
    if boundary.empty or boundary.crs is None:
        raise ValueError("Municipality boundary must be nonempty and define a CRS")
    bounds = boundary.to_crs("EPSG:4326").geometry.union_all()
    selected = [
        tile.path
        for tile in grid_catalog(input_dir, cache_dir)
        if box(*tile.bbox_wgs84).intersects(bounds)
    ]
    if not selected:
        raise ValueError("No population grid covers the requested municipality")
    return selected
