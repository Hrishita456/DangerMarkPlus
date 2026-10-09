from collections import deque
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask, shapes
from shapely.geometry import GeometryCollection, shape
from shapely.ops import unary_union

from .spatial import project


@dataclass
class FloodExtent:
    geometry: object
    known_area: object
    source: str
    reasons: list[str]


def connected_mask(eligible, seeds):
    """Four-neighbour connectivity; nodata and high terrain are barriers."""
    wet = np.zeros(eligible.shape, dtype=bool)
    pending = deque(map(tuple, np.argwhere(eligible & seeds)))
    for row, col in pending:
        wet[row, col] = True
    while pending:
        row, col = pending.popleft()
        for r, c in ((row-1, col), (row+1, col), (row, col-1), (row, col+1)):
            if 0 <= r < wet.shape[0] and 0 <= c < wet.shape[1] and eligible[r, c] and not wet[r, c]:
                wet[r, c] = True
                pending.append((r, c))
    return wet


def polygonize(mask, transform):
    return unary_union([shape(g) for g, value in shapes(mask.astype("uint8"), mask=mask, transform=transform) if value]) if mask.any() else GeometryCollection()


def terrain_extent(path, hydrography, boundary, crs, spec):
    with rasterio.open(path) as src:
        if src.crs != crs or src.count != 1:
            raise ValueError("DEM must be single-band in the configured metric CRS")
        values = src.read(1, masked=True)
        valid = ~np.ma.getmaskarray(values) & np.isfinite(values.data)
        inside = geometry_mask([boundary], values.shape, src.transform, invert=True)
        rivers = hydrography[hydrography.waterway.isin(spec.seed_waterway_types)]
        if rivers.empty:
            raise ValueError("No configured river seed geometries")
        seeds = geometry_mask(list(rivers.geometry.buffer(spec.seed_buffer_m)), values.shape, src.transform, invert=True)
        eligible = valid & inside & (values.data <= spec.water_surface_m)
        if not (seeds & eligible).any():
            raise ValueError("Assumed surface has no eligible river seed; extent is undefined")
        wet = connected_mask(eligible, seeds)
        # Known coverage is valid raster footprint, not the centre-selected flood mask.
        known = polygonize(valid, src.transform).intersection(boundary)
        geometry = polygonize(wet, src.transform).intersection(boundary)
    return FloodExtent(geometry, known, spec.source, [spec.assumption,
        "Four-neighbour low DSM cells connected to mapped river seeds; no hydraulics, levee or drainage model.",
        "Water bodies are included; this is not an estimate of newly inundated dry land.",
        "Nodata blocks propagation and remains unknown, never known dry."])


def load_extent(path, boundary, crs, source, assumption):
    """Trusted server-configured polygon or binary raster, never RGB evidence imagery."""
    if path.suffix.lower() in {".tif", ".tiff"}:
        with rasterio.open(path) as src:
            if not src.crs or src.count != 1:
                raise ValueError("Flood mask must be single-band with a CRS; RGB evidence is not a mask")
            values = src.read(1, masked=True)
            valid = ~np.ma.getmaskarray(values) & np.isfinite(values.data)
            if not set(np.unique(values.data[valid])).issubset({0, 1}):
                raise ValueError("Classified flood mask must contain only 0/1 and nodata")
            geometry = project(polygonize(valid & (values.data == 1), src.transform), src.crs, crs)
            known = project(polygonize(valid, src.transform), src.crs, crs)
    else:
        frame = gpd.read_file(path)
        if not frame.crs or not frame.geometry.is_valid.all() or not frame.geom_type.isin(["Polygon", "MultiPolygon"]).all():
            raise ValueError("Flood vector requires valid polygons and CRS")
        geometry = frame.to_crs(crs).geometry.union_all()
        known = boundary  # Configured polygon means a complete extent within the pilot.
    return FloodExtent(geometry.intersection(boundary), known.intersection(boundary), source,
                       [assumption, "Precomputed vector assumes complete extent coverage; raster nodata remains unknown."])
