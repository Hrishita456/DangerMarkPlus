"""Create a deterministic, region-configured bundle from cached sources (no network)."""
import argparse
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (CATALOG, CONFIG_PATH, PROCESSED, ROOT, config, file_record,
                    manifest_path, read_json, record_processing, sha256, write_json)
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from pypdf import PdfReader
import pypdfium2 as pdfium
from pyproj import CRS, Transformer
import rasterio
from rasterio.control import GroundControlPoint
from rasterio.features import geometry_mask
from rasterio.transform import from_gcps, from_origin
from rasterio.warp import Resampling, reproject
from shapely import STRtree, area, box, intersection, make_valid
from shapely.geometry import Point, Polygon, mapping
from shapely.ops import transform


def source_path(dataset_id):
    manifest = read_json(manifest_path(dataset_id))
    for record in manifest["raw_files"]:
        if sha256(ROOT / record["path"]) != record["sha256"]:
            raise ValueError(f"Raw checksum changed: {record['path']}")
    return ROOT / manifest["raw_files"][0]["path"]


def study_geometry(pilot):
    crs = CRS.from_user_input(pilot["metric_crs"])
    if not crs.is_projected or any(axis.unit_name != "metre" for axis in crs.axis_info):
        raise ValueError("Metric CRS must use metres")
    west, south, east, north = pilot["bbox_wgs84"]
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Invalid WGS84 bounds")
    wgs = box(west, south, east, north).segmentize(0.002)
    forward = Transformer.from_crs(4326, crs, always_xy=True).transform
    return wgs, transform(forward, wgs)


def grid_for(pilot, boundary, resolution):
    snap = pilot["grid_snap_m"]
    if snap % resolution:
        raise ValueError("Raster resolution must divide the common grid snap")
    left, bottom, right, top = boundary.bounds
    left, bottom = math.floor(left / snap) * snap, math.floor(bottom / snap) * snap
    right, top = math.ceil(right / snap) * snap, math.ceil(top / snap) * snap
    return {"crs": pilot["metric_crs"], "transform": from_origin(left, top, resolution, resolution),
            "width": round((right - left) / resolution), "height": round((top - bottom) / resolution),
            "bounds": [left, bottom, right, top], "resolution_m": resolution}


def save_raster(path, values, grid, nodata, **tags):
    path.parent.mkdir(parents=True, exist_ok=True)
    if values.ndim == 2:
        values = values[np.newaxis, ...]
    with rasterio.open(path, "w", driver="GTiff", width=grid["width"], height=grid["height"],
                       count=len(values), dtype=values.dtype, crs=grid["crs"], transform=grid["transform"],
                       nodata=nodata, compress="deflate", tiled=True, blockxsize=256, blockysize=256) as out:
        out.write(values)
        out.update_tags(**{key: str(value) for key, value in tags.items()})
    return path


def raster_metadata(path):
    with rasterio.open(path) as dataset:
        return {"path": str(path.relative_to(ROOT)), "crs": str(dataset.crs), "bounds": list(dataset.bounds),
                "resolution": list(dataset.res), "shape": [dataset.height, dataset.width],
                "bands": dataset.count, "nodata": dataset.nodata, "dtype": dataset.dtypes[0],
                "scales": list(dataset.scales), "offsets": list(dataset.offsets), "tags": dataset.tags()}


def save_features(path, records):
    records = sorted(records, key=lambda f: str(f["properties"]["id"]))
    write_json(path, {"type": "FeatureCollection", "features": records})
    return path


def feature(geometry, properties):
    return {"type": "Feature", "geometry": mapping(geometry), "properties": properties}


def prepare_boundary(pilot, wgs, metric):
    path = save_features(PROCESSED / "region/boundary.geojson", [feature(wgs, {
        "id": pilot["id"], "name": pilot["name"], "classification": "analysis_boundary_assumption",
        "area_km2": metric.area / 1e6, "metric_crs": pilot["metric_crs"],
    })])
    write_json(CATALOG / "manifests/region.json", {
        "id": "region", "name": pilot["name"], "provider": "Project analysis configuration",
        "url": str(CONFIG_PATH.relative_to(ROOT)), "license": "Project configuration",
        "classification": "assumption", "original_crs": "EPSG:4326", "processed_crs": "EPSG:4326",
        "configuration_sha256": sha256(CONFIG_PATH),
        "spatial_resolution": "Configured rectangle", "temporal_coverage": None,
        "raw_files": [], "processed_files": [file_record(path)],
        "preprocessing_steps": ["Densify rectangle edges before metric projection", "Area computed in projected metres"],
        "limitations": ["Not an administrative boundary, observed flood extent or catchment"],
    })
    return path


def prepare_dem(pilot, metric, dataset_id):
    grid = grid_for(pilot, metric, pilot["dem_resolution_m"])
    values = np.full((grid["height"], grid["width"]), pilot["nodata"], dtype="float32")
    with rasterio.open(source_path(dataset_id)) as src:
        if src.scales != (1.0,) or src.offsets != (0.0,):
            raise ValueError('Scaled elevation values require an explicit source adapter')
        reproject(rasterio.band(src, 1), values, src_transform=src.transform, src_crs=src.crs,
                  src_nodata=src.nodata, dst_transform=grid["transform"], dst_crs=grid["crs"],
                  dst_nodata=pilot["nodata"], resampling=Resampling.bilinear)
    outside = geometry_mask([mapping(metric)], values.shape, grid["transform"], invert=False)
    values[outside] = pilot["nodata"]
    path = save_raster(PROCESSED / f"elevation/dem_{pilot['dem_resolution_m']}m.tif", values, grid, pilot["nodata"],
                       units="metres", resampling="bilinear", vertical_reference="EGM2008", interpretation="surface elevation, not bare-earth")
    record_processing(dataset_id, [path], ["Bilinear projection to configured metric grid", "Mask outside pixel-centre study boundary"],
                      grid["crs"], raster=raster_metadata(path), native_subset_raster=raster_metadata(source_path(dataset_id)))
    return path


def conservative_population(src, metric, grid, nodata=-9999):
    """Transfer counts by projected cell-overlap area; unknown cells stay unknown.

    Assumption: uniform population within each native cell. Each destination value
    is persons in its intersection with the study boundary, not persons per m².
    """
    source = src.read(1, masked=True)
    valid = (~np.ma.getmaskarray(source)) & np.isfinite(source.data) & (source.data >= 0)
    rows, cols = np.where(valid)
    convert = Transformer.from_crs(src.crs, grid["crs"], always_xy=True).transform
    cells, clipped, counts = [], [], []
    for row, col in zip(rows, cols):
        corners = [src.transform * (col, row), src.transform * (col + 1, row),
                   src.transform * (col + 1, row + 1), src.transform * (col, row + 1)]
        cell = transform(convert, Polygon(corners))
        overlap = cell.intersection(metric)
        if overlap.area > 0:
            cells.append(cell); clipped.append(overlap); counts.append(float(source.data[row, col]))
    if not cells:
        raise ValueError("No valid population cells overlap the study region")
    cell_areas = area(cells)
    densities = np.asarray(counts) / cell_areas  # internal weight only; outputs are counts
    expected = float(np.dot(densities, area(clipped)))
    clipped_array = np.asarray(clipped, dtype=object)
    tree = STRtree(clipped_array)
    values = np.full((grid["height"], grid["width"]), float(nodata), dtype="float64")
    coverage = np.zeros_like(values, dtype="float32")
    for row in range(grid["height"]):
        for col in range(grid["width"]):
            left, top = grid["transform"] * (col, row)
            right, bottom = grid["transform"] * (col + 1, row + 1)
            target = box(left, bottom, right, top).intersection(metric)
            if target.area <= 0:
                continue
            ids = tree.query(target, predicate="intersects")
            if not len(ids):
                continue
            weights = area(intersection(clipped_array[ids], target))
            known_area = float(weights.sum())
            if known_area > 0:
                values[row, col] = np.dot(densities[ids], weights)
                coverage[row, col] = min(1, known_area / target.area)
    actual = float(values[values >= 0].sum())
    return values, coverage, {"source_valid_cell_count": len(cells), "source_fractional_pilot_total": expected,
                               "aligned_pilot_total": actual, "absolute_conservation_error": abs(actual - expected),
                               "source_nodata_reinterpreted_as_zero": False}


def prepare_population(pilot, metric, dataset_id):
    grid = grid_for(pilot, metric, pilot["population_resolution_m"])
    source_manifest = read_json(manifest_path(dataset_id))
    with rasterio.open(source_path(dataset_id)) as src:
        if src.scales != (1.0,) or src.offsets != (0.0,):
            raise ValueError('Scaled population values require an explicit source adapter')
        values, coverage, totals = conservative_population(src, metric, grid, pilot['nodata'])
    paths = [save_raster(PROCESSED / f"population/population_{pilot['population_resolution_m']}m.tif", values, grid, pilot['nodata'],
                         units="persons per grid cell within study boundary", resampling="conservative projected area overlap",
                         assumption="uniform distribution within each native pixel; no new detail",
                         native_resolution_m_nominal=source_manifest.get('native_resolution_m_nominal', 'see source manifest'),
                         native_resolution_degrees=source_manifest['source_resolution_degrees'],
                         fine_grid_is_alignment_only=True),
             save_raster(PROCESSED / f"population/known_coverage_fraction_{pilot['population_resolution_m']}m.tif", coverage, grid, None,
                         units="fraction of study-intersection area covered by valid source cells", resampling="area overlap")]
    record_processing(dataset_id, paths, ["Retain native-grid input", "Project native cell polygons using always_xy",
                       "Allocate counts by exact polygon intersection area", "Keep source nodata unknown; record coverage fraction"],
                      grid["crs"], rasters=[raster_metadata(p) for p in paths], conservation=totals,
                      native_subset_raster=raster_metadata(source_path(dataset_id)),
                      effective_spatial_resolution=source_manifest['spatial_resolution'],
                      fine_grid_is_alignment_only=True)
    return paths


def prepare_roads(pilot, wgs, metric):
    ox.settings.useful_tags_way = sorted(set(ox.settings.useful_tags_way + ["bridge", "tunnel", "layer", "access", "motor_vehicle", "motorcar", "maxspeed", "surface", "lanes"]))
    graph = ox.graph_from_xml(source_path("osm_roads"), simplify=False, retain_all=True)
    inverse = Transformer.from_crs(pilot["metric_crs"], 4326, always_xy=True).transform
    graph = ox.truncate.truncate_graph_polygon(graph, transform(inverse, metric.buffer(pilot["road_buffer_m"])), truncate_by_edge=False)
    graph = ox.simplify_graph(graph, edge_attrs_differ=["bridge", "tunnel", "layer", "highway", "maxspeed"])
    graph = ox.project_graph(graph, to_crs=pilot["metric_crs"])
    assumed = 0
    for u, v, key, edge in graph.edges(keys=True, data=True):
        # Use projected geometry lengths rather than decimal-degree distances.
        geom = edge.get("geometry")
        if geom is None:
            from shapely.geometry import LineString
            geom = LineString([(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])])
            edge["geometry"] = geom
        edge["length"] = float(geom.length)
        speeds = edge.get("maxspeed", [])
        speeds = speeds if isinstance(speeds, list) else [speeds]
        parsed = []
        for speed in speeds:
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kph)?\s*", str(speed))
            if match and float(match[1]) > 0:
                parsed.append(float(match[1]) * (1.609344 if match[2] == "mph" else 1))
        highway = edge.get("highway", "road")
        highway = highway if isinstance(highway, list) else [highway]
        speed = min(parsed) if parsed else min(pilot["speed_assumptions_kph"].get(kind, 20) for kind in highway)
        edge["speed_kph"] = speed
        edge["speed_source"] = "osm_maxspeed_tag" if parsed else "configured_class_assumption"
        edge["travel_time"] = edge["length"] / (speed / 3.6)
        edge["travel_time_status"] = "free_flow_estimate_not_flood_evacuation_time"
        assumed += not bool(parsed)
    graph.graph.update(region_id=pilot["id"], snapshot_at=pilot["osm_snapshot_at"], network_type="motor_vehicle",
                       source="OpenStreetMap contributors", travel_time_units="seconds", length_units="metres",
                       created_date=pilot["osm_snapshot_at"])
    # OSMnx merges tags through sets. Canonicalize unordered lists for repeatable
    # exports across Python processes; coordinate order in geometries is untouched.
    for attributes in [graph.graph, *[attrs for _, attrs in graph.nodes(data=True)],
                       *[attrs for *_, attrs in graph.edges(data=True, keys=True)]]:
        for key, value in attributes.items():
            if isinstance(value, list):
                attributes[key] = sorted(value, key=str)
    path = PROCESSED / "roads/roads.graphml"; path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, path)
    nodes, edges = ox.graph_to_gdfs(graph)
    geopackage = path.with_name("roads.gpkg")
    if geopackage.exists():
        geopackage.unlink()  # deterministic regeneration of our derived file only
    nodes.to_file(geopackage, layer="nodes", driver="GPKG")
    # Lists remain in GraphML; serialize list-valued tags in GIS export.
    for column in edges.columns:
        if column != "geometry":
            edges[column] = edges[column].map(lambda value: str(value) if isinstance(value, (list, tuple)) else value)
    edges.to_file(geopackage, layer="edges", driver="GPKG")
    import sqlite3
    with sqlite3.connect(geopackage) as connection:
        connection.execute("UPDATE gpkg_contents SET last_change = ?", (pilot["osm_snapshot_at"],))
    record_processing("osm_roads", [path, geopackage], ["Build directed OSMnx graph preserving one-way tags and all components",
                      "Truncate to metric 500m buffer", "Simplify without merging changes in bridge/tunnel/layer/class/speed",
                      "Project and calculate metre lengths", "Preserve maxspeed; explicitly flag fallback class speeds"],
                      pilot["metric_crs"], graph_statistics={"nodes": len(graph), "edges": graph.number_of_edges(),
                      "weak_components": nx.number_weakly_connected_components(graph), "assumed_speed_edges": assumed},
                      limitations=list(dict.fromkeys(read_json(manifest_path("osm_roads"))["limitations"] + ["No turn-restriction relations; conditional access is not evaluated", "Not a flood routing result; disconnected components retained"])))
    return [path, geopackage]


def prepare_features(pilot, metric, dem_path):
    import pandas as pd
    feature_ids = ["osm_hydrography", "osm_communities", "osm_safe_sites"]
    frames = [ox.features_from_xml(source_path(dataset_id)) for dataset_id in feature_ids]
    source_members = {dataset_id: set(frame.index) for dataset_id, frame in zip(feature_ids, frames)}
    all_features = gpd.GeoDataFrame(pd.concat(frames), crs="EPSG:4326")
    all_features = all_features[~all_features.index.duplicated()]
    all_features = all_features.to_crs(pilot["metric_crs"])
    reverse = Transformer.from_crs(pilot["metric_crs"], 4326, always_xy=True).transform
    groups = {"hydrography": [], "communities": [], "safe_sites": []}
    def text(row, key):
        value = row.get(key)
        return value if isinstance(value, str) and value else None
    for (element, osm_id), row in all_features.sort_index().iterrows():
        geometry = make_valid(row.geometry).intersection(metric)
        if geometry.is_empty:
            continue
        props = {"id": f"osm/{element}/{osm_id}", "name": text(row, "name"), "source": "OpenStreetMap",
                 "source_url": f"https://www.openstreetmap.org/{element}/{osm_id}", "snapshot_at": pilot["osm_snapshot_at"]}
        if (element, osm_id) in source_members['osm_hydrography'] and (text(row, "waterway") in ("river", "stream", "canal", "drain", "riverbank") or text(row, "natural") == "water"):
            groups["hydrography"].append(feature(transform(reverse, geometry), {**props, "waterway": text(row, "waterway"),
                        "water": text(row, "water"), "representation": "mapped_water_geometry_not_flood_extent"}))
        point = geometry if geometry.geom_type == "Point" else geometry.representative_point()
        wgs_point = transform(reverse, point)
        point_props = {**props, "longitude": wgs_point.x, "latitude": wgs_point.y,
                       "representation": "osm_point" if geometry.geom_type == "Point" else "point_on_clipped_osm_geometry",
                       "population": None, "population_source": None}
        if (element, osm_id) in source_members['osm_communities'] and text(row, "place") in ("neighbourhood", "suburb", "quarter", "locality", "village", "hamlet", "isolated_dwelling") and props["name"]:
            groups["communities"].append(feature(wgs_point, {**point_props, "type": text(row, "place"),
                         "is_administrative_boundary": False}))
        kind = text(row, "amenity")
        if (element, osm_id) in source_members['osm_safe_sites'] and (kind in ("school", "college", "university", "hospital", "community_centre", "townhall", "social_facility") or text(row, "office") == "government"):
            with rasterio.open(dem_path) as dem:
                elevation = next(dem.sample([(point.x, point.y)], masked=True))[0]
            groups["safe_sites"].append(feature(wgs_point, {**point_props, "type": kind or "government_office",
                       "osm_access": text(row, "access"), "osm_operator": text(row, "operator"),
                       "osm_operator_type": text(row, "operator:type"), "osm_ownership": text(row, "ownership"),
                       "verification_status": "unverified_candidate", "capacity": None, "capacity_source": None,
                       "elevation_m": None if np.ma.is_masked(elevation) else float(elevation),
                       "elevation_source": "Copernicus DSM sampled at representative point", "safety_assessed": False}))
    names = {"hydrography": "hydrography.geojson", "communities": "localities.geojson", "safe_sites": "candidates.geojson"}
    paths = [save_features(PROCESSED / category / names[category], records) for category, records in groups.items()]
    for (category, records), path in zip(groups.items(), paths):
        record_processing(f"osm_{category}", [path], ["Read complete OSM XML geometries", "Repair invalid geometries in projected CRS and clip to study polygon",
                           "Preserve mapped locality nodes or use points on mapped polygons", "All facility capacities unknown; no safety assessment",
                           "Export GeoJSON longitude, latitude in WGS84"], "EPSG:4326", feature_count=len(records))
    return paths


def prepare_gauge(pilot):
    gauge = pilot["gauge"]
    for dataset_id in gauge["source_ids"]:
        source_path(dataset_id)
    path = save_features(PROCESSED / "gauge/station.geojson", [feature(Point(gauge["longitude"], gauge["latitude"]),
                        {**gauge, "classification": "historical_reference", "is_synthetic": False})])
    # Only documented observations: no generated time series or interpolation.
    observations = PROCESSED / "gauge/observations.json"
    write_json(observations, {"station_id": gauge["id"], "timezone": pilot["timezone"],
                "vertical_reference": gauge["vertical_reference"], "observations": [
                    {"at": gauge["peak_at"], "level_m": gauge["peak_level_m"], "kind": "reported_event_peak",
                     "source_id": gauge["source_ids"][0]}], "interpolated": False})
    for dataset_id in gauge["source_ids"]:
        record_processing(dataset_id, [path, observations], ["Transcribe explicitly documented catalogue/reference values",
                          "Preserve rounded coordinate and unresolved vertical datum caveats", "No time-series fabrication"], "EPSG:4326")
    return [path, observations]


def prepare_flood(pilot, metric, sources):
    paths, footprints = [], []
    for dataset_id, source in sources.items():
        if source["category"] != "flood":
            continue
        pdf_path = source_path(dataset_id)
        page = PdfReader(pdf_path).pages[0]
        viewports = [item.get_object() for item in page.get("/VP", [])]
        name = source.get("map_viewport", "During Flood")
        matches = [vp for vp in viewports if vp.get("/Name") == name]
        if len(matches) != 1:
            raise ValueError(f"Expected one explicit map viewport {name}: {dataset_id}")
        vp = matches[0]; measure = vp["/Measure"].get_object()
        map_crs = CRS.from_wkt(str(measure["/GCS"]["/WKT"]))
        controls = np.asarray(measure["/GPTS"], dtype=float).reshape(-1, 2)
        local = np.asarray(measure["/LPTS"], dtype=float).reshape(-1, 2)
        # ISO GeoPDF GPTS order is latitude, longitude; export flips to GeoJSON order.
        projected = Transformer.from_crs(4326, map_crs, always_xy=True).transform(controls[:, 1], controls[:, 0])
        x0, top_pdf, x1, bottom_pdf = map(float, vp["/BBox"])
        if not (x0 < x1 and bottom_pdf < top_pdf):
            raise ValueError("Unsupported PDF viewport orientation; do not guess georeferencing")
        scale = .5
        document = pdfium.PdfDocument(pdf_path)
        image = document[0].render(scale=scale).to_pil().convert("RGB")
        page_height = float(page.mediabox.height)
        left, top = math.floor(x0 * scale), math.floor((page_height - top_pdf) * scale)
        right, bottom = math.ceil(x1 * scale), math.ceil((page_height - bottom_pdf) * scale)
        pixels = np.asarray(image.crop((left, top, right, bottom)))
        gcps = [GroundControlPoint(row=(page_height - top_pdf + py * (top_pdf - bottom_pdf)) * scale - top,
                                   col=(x0 + px * (x1 - x0)) * scale - left, x=x, y=y)
                for (px, py), x, y in zip(local, *projected)]
        affine = from_gcps(gcps)
        residual = max(math.hypot(*(np.subtract(affine * (p.col, p.row), (p.x, p.y)))) for p in gcps)
        if residual > 5:
            raise ValueError(f"Unexpected GeoPDF control residual: {residual}m")
        grid = grid_for(pilot, metric, pilot["dem_resolution_m"])
        rgba = np.zeros((4, grid["height"], grid["width"]), dtype="uint8")
        for band in range(3):
            reproject(pixels[:, :, band], rgba[band], src_transform=affine, src_crs=map_crs,
                      dst_transform=grid["transform"], dst_crs=grid["crs"], resampling=Resampling.nearest)
        reproject(np.full(pixels.shape[:2], 255, dtype="uint8"), rgba[3], src_transform=affine, src_crs=map_crs,
                  dst_transform=grid["transform"], dst_crs=grid["crs"], resampling=Resampling.nearest)
        rgba[:, geometry_mask([mapping(metric)], rgba.shape[1:], grid["transform"])] = 0
        path = save_raster(PROCESSED / f"flood/{dataset_id}_evidence_{pilot['dem_resolution_m']}m.tif", rgba, grid, None,
                           interpretation="cartographic satellite evidence, NOT a binary flood mask", resampling="nearest", alpha_band=4)
        with rasterio.open(path, "r+") as out:
            out.colorinterp = (rasterio.enums.ColorInterp.red, rasterio.enums.ColorInterp.green,
                               rasterio.enums.ColorInterp.blue, rasterio.enums.ColorInterp.alpha)
        # This polygon is map coverage only, never the flooded area.
        footprint = Polygon([(lon, lat) for lat, lon in controls])
        footprints.append(feature(footprint, {"id": dataset_id, "source_url": source["url"],
                          "representation": "map_coverage_not_flood_extent", "temporal_coverage": source["temporal_coverage"]}))
        record_processing(dataset_id, [path], ["Read embedded GeoPDF viewport and GCS WKT", "Render and crop map viewport, excluding legend/insets",
                           "Fit affine transform in embedded map CRS from four geographic controls", "Project onto common 30m grid; retain labels/clouds; no classification"],
                          pilot["metric_crs"], raster=raster_metadata(path), embedded_map_crs=map_crs.to_string(),
                          max_control_fit_residual_m=residual, source_control_points_lat_lon=controls.tolist(),
                          map_coverage_wgs84=mapping(footprint), quantitative_flood_mask=False)
        paths.append(path)
        document.close()
    footprints_path = save_features(PROCESSED / "flood/evidence_coverage.geojson", footprints)
    for dataset_id, source in sources.items():
        if source["category"] == "flood":
            manifest = read_json(manifest_path(dataset_id))
            manifest["processed_files"].append(file_record(footprints_path))
            write_json(manifest_path(dataset_id), manifest)
    return paths + [footprints_path]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["rasters", "population", "roads", "features", "references"])
    args = parser.parse_args()
    pilot = config(); sources = read_json(CATALOG / "sources.json")
    wgs, metric = study_geometry(pilot)
    if args.only != 'population' or not (PROCESSED / 'region/boundary.geojson').exists():
        prepare_boundary(pilot, wgs, metric)
    if args.only in (None, "rasters", "population"):
        for category, function in (("elevation", prepare_dem), ("population", prepare_population)):
            if args.only == 'population' and category != 'population':
                continue
            dataset_id = next(key for key, value in sources.items() if value["category"] == category)
            print(f"Preparing {category}", flush=True); function(pilot, metric, dataset_id)
    if args.only in (None, "roads"):
        print("Preparing road graph", flush=True); prepare_roads(pilot, wgs, metric)
    if args.only in (None, "features"):
        print("Preparing mapped features", flush=True)
        prepare_features(pilot, metric, PROCESSED / f"elevation/dem_{pilot['dem_resolution_m']}m.tif")
    if args.only in (None, "references"):
        print("Preparing gauge and flood evidence", flush=True)
        prepare_gauge(pilot); prepare_flood(pilot, metric, sources)


if __name__ == "__main__":
    main()
