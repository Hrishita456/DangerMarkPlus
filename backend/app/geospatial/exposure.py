import numpy as np
import rasterio
from shapely.geometry import Polygon
from shapely.strtree import STRtree
from .spatial import project


class Population:
    """Native people-per-pixel counts integrated over projected pixel intersections."""
    def __init__(self, cells, counts, source, rounding=100, resolution_note="Native pixel resolution; no subpixel demographic detail."):
        self.cells = cells
        self.counts = counts
        self.tree = STRtree(cells)
        self.source = source
        self.rounding = rounding
        self.resolution_note = resolution_note

    @classmethod
    def load(cls, path, crs, source, rounding, resolution_note="Native pixel resolution; no subpixel demographic detail."):
        cells, counts = [], []
        with rasterio.open(path) as src:
            if not src.crs or src.count != 1:
                raise ValueError("Population requires a single-band raster and CRS")
            values = src.read(1, masked=True)
            valid = ~np.ma.getmaskarray(values) & np.isfinite(values.data)
            if np.any(values.data[valid] < 0):
                raise ValueError("Negative population counts")
            for row, col in np.argwhere(valid):
                corners = [src.transform * point for point in [(col,row),(col+1,row),(col+1,row+1),(col,row+1)]]
                cells.append(project(Polygon(corners), src.crs, crs))
                counts.append(float(values.data[row,col]))
        return cls(cells, counts, source, rounding, resolution_note)

    def exposure(self, area):
        total, covered = 0.0, 0.0
        for idx in self.tree.query(area, predicate="intersects"):
            intersection = area.intersection(self.cells[idx]).area
            covered += intersection
            total += self.counts[idx] * intersection / self.cells[idx].area
        coverage = min(1.0, covered / area.area) if area.area else 1.0
        return {"exposed_population": round(total / self.rounding) * self.rounding if coverage > 0 else None,
                "coverage_fraction": round(coverage, 6), "population_source": self.source,
                "estimate_kind": "known_coverage_estimate" if coverage >= .999999 else "partial_coverage_lower_bound",
                "rounding_people": self.rounding,
                "assumptions": ["Uniform population within each native pixel; people-per-pixel counts, not density.",
                    self.resolution_note,
                    "Raster model population is not event-day occupancy or evacuation demand."]}
