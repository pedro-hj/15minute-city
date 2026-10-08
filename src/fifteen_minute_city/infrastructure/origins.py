from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from scipy.spatial import cKDTree

from fifteen_minute_city.domain.models import Origin, OriginSet


def _grid_data_source(grid_path: Path) -> str:
    if grid_path.suffix.lower() == ".zip":
        return f"zip://{grid_path}"
    return str(grid_path)


def _read_population_grid(
    path: str | Path,
    boundary: gpd.GeoDataFrame | None,
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    source = _grid_data_source(Path(path).expanduser().resolve())
    if boundary is None:
        grid = gpd.read_file(source)
        return grid, {"spatially_filtered": False, "loaded_feature_count": len(grid)}

    if boundary.empty:
        raise ValueError("municipality boundary must not be empty")
    if boundary.crs is None:
        raise ValueError("municipality boundary must define a CRS")

    sample = gpd.read_file(source, rows=1)
    if sample.crs is None:
        raise ValueError("population grid must define a CRS")
    boundary_in_grid_crs = boundary.to_crs(sample.crs)
    grid = gpd.read_file(source, bbox=tuple(boundary_in_grid_crs.total_bounds))
    candidate_count = len(grid)
    if grid.empty:
        raise ValueError("population grid does not intersect the municipality boundary")

    valid_geometry = grid.geometry.notna() & ~grid.geometry.is_empty
    grid = grid.loc[valid_geometry].copy()
    municipality = boundary_in_grid_crs.geometry.union_all()
    representative_points = grid.geometry.representative_point()
    grid = grid.loc[representative_points.covered_by(municipality)].copy()
    if grid.empty:
        raise ValueError(
            "population grid has no cell representative points inside the municipality"
        )
    return grid, {
        "spatially_filtered": True,
        "spatial_filter_method": "representative_point_covered_by",
        "candidate_feature_count": candidate_count,
        "municipality_feature_count": len(grid),
        "boundary_crs": str(boundary.crs),
    }


def origins_from_graph_nodes(graph: nx.Graph) -> OriginSet:
    """Build the unweighted graph-node baseline used to quantify spatial bias."""
    origins = tuple(
        Origin(origin_id=f"node:{node}", node_id=int(node), weight=1.0)
        for node in graph.nodes
    )
    return OriginSet(
        strategy="network_nodes",
        weight_unit="node_count",
        origins=origins,
        metadata={"node_count": len(origins)},
    )


def load_population_grid(
    path: str | Path | Sequence[str | Path],
    graph: nx.MultiDiGraph,
    *,
    population_column: str = "population",
    id_column: str | None = None,
    boundary: gpd.GeoDataFrame | None = None,
) -> OriginSet:
    """Load, municipally filter, and snap a population grid to the graph."""
    paths = [path] if isinstance(path, (str, Path)) else list(path)
    if not paths:
        raise ValueError("at least one population grid is required")
    grid_paths = [Path(item).expanduser().resolve() for item in paths]
    grids = []
    metadata_by_tile = []
    for grid_path in grid_paths:
        if not grid_path.is_file():
            raise FileNotFoundError(f"population grid not found: {grid_path}")
        try:
            part, tile_metadata = _read_population_grid(grid_path, boundary)
        except ValueError as exc:
            if len(grid_paths) > 1 and str(exc) in (
                "population grid does not intersect the municipality boundary",
                "population grid has no cell representative points inside the municipality",
            ):
                continue
            raise
        grids.append(part.to_crs("EPSG:4326"))
        metadata_by_tile.append({"file": grid_path.name, **tile_metadata})
    if not grids:
        raise ValueError("no populated grid tiles intersect the municipality")

    grid = gpd.GeoDataFrame(
        pd.concat(grids, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    if id_column is not None and len(grid_paths) > 1:
        grid = grid.drop_duplicates(subset=[id_column], keep="first").copy()
    spatial_metadata = (
        metadata_by_tile[0]
        if len(grid_paths) == 1
        else {
            "spatially_filtered": boundary is not None,
            "source_tiles": [item["file"] for item in metadata_by_tile],
            "candidate_tile_count": len(grid_paths),
            "selected_tile_count": len(metadata_by_tile),
        }
    )
    loaded_feature_count = len(grid)
    if grid.empty:
        raise ValueError("population grid must contain at least one feature")
    if grid.crs is None:
        raise ValueError("population grid must define a CRS")
    if population_column not in grid.columns:
        raise ValueError(f"population grid is missing column '{population_column}'")
    if id_column is not None and id_column not in grid.columns:
        raise ValueError(f"population grid is missing ID column '{id_column}'")

    valid_geometry = grid.geometry.notna() & ~grid.geometry.is_empty
    grid = grid.loc[valid_geometry].copy()
    grid[population_column] = pd.to_numeric(grid[population_column], errors="coerce")
    if grid[population_column].isna().any():
        raise ValueError("population values must be numeric")
    if (grid[population_column] < 0).any():
        raise ValueError("population values must not be negative")
    grid = grid.loc[grid[population_column] > 0].copy()
    if grid.empty:
        raise ValueError("population grid has no cells with positive population")

    origin_metadata = {
        "population_column": population_column,
        "id_column": id_column,
        "loaded_feature_count": loaded_feature_count,
        "positive_population_feature_count": len(grid),
        "total_population": float(grid[population_column].sum()),
        "source_crs": str(grid.crs),
        **spatial_metadata,
    }

    try:
        projected_grid = grid.to_crs(grid.estimate_utm_crs())
        positive_areas = projected_grid.geometry.area
        positive_areas = positive_areas[positive_areas > 0]
        if not positive_areas.empty:
            origin_metadata["median_cell_area_square_meters"] = float(
                positive_areas.median()
            )
    except (ValueError, RuntimeError):
        pass

    grid = grid.to_crs("EPSG:4326")
    projected_points = grid.geometry.representative_point()
    graph_crs = graph.graph.get("crs")
    if graph_crs is None:
        raise ValueError("walking graph must define a CRS")
    if ox.projection.is_projected(graph_crs):
        projected_graph = graph
    else:
        projected_graph = ox.project_graph(graph)
    projected_points = projected_points.to_crs(projected_graph.graph["crs"])

    graph_node_ids = list(projected_graph.nodes)
    if not graph_node_ids:
        raise ValueError("walking graph must not be empty")
    node_coordinates = np.asarray(
        [
            (projected_graph.nodes[node]["x"], projected_graph.nodes[node]["y"])
            for node in graph_node_ids
        ]
    )
    tree = cKDTree(node_coordinates)
    point_coordinates = np.asarray([(point.x, point.y) for point in projected_points])
    _distances, nearest_indices = tree.query(point_coordinates, k=1)
    node_ids = [graph_node_ids[int(index)] for index in nearest_indices]

    origins = []
    for position, (index, row) in enumerate(grid.iterrows()):
        source_id = row[id_column] if id_column else index
        origins.append(
            Origin(
                origin_id=f"grid:{source_id}",
                node_id=int(node_ids[position]),
                weight=float(row[population_column]),
            )
        )

    return OriginSet(
        strategy="population_grid",
        weight_unit="population",
        origins=tuple(origins),
        source=";".join(str(item) for item in grid_paths),
        metadata=origin_metadata,
    )
