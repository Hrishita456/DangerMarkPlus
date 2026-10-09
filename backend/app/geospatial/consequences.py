"""Region-independent engine; all study choices live in Scenario/bundle configuration."""
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import osmnx as ox
from pyproj import CRS

from .connectivity import Connectivity
from .exposure import Population
from .flood import load_extent, terrain_extent
from .roads import evaluate_roads
from .spatial import collection, feature, metric_crs

ALGORITHM_VERSION = "phase3-1.0.2"


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def repository_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Configured dataset path must stay inside the repository")
    return path


@dataclass
class Region:
    bundle: dict
    bundle_hash: str
    crs: object
    boundary: object
    hydrography: object
    localities: object
    graph: object
    population: object
    dem_path: Path

    @classmethod
    def load(cls, root, bundle_path, rounding):
        bundle = json.loads(bundle_path.read_text())
        crs = metric_crs(bundle['metric_crs'])
        inputs = bundle['inputs']
        # Verify referenced data once per cached bundle load, including unused evidence.
        records = [f for item in inputs.values() for f in item['files']]
        records.append(inputs['population']['native_source_subset'])
        records.extend(bundle[key] for key in ('configuration', 'source_catalogue', 'validation_report', 'toolchain_lock'))
        for record in records:
            path = repository_path(root, record['path'])
            if not path.is_file() or digest(path) != record['sha256']:
                raise ValueError(f"Missing or changed bundle input: {record['path']}")
        def path(key):
            return repository_path(root, inputs[key]['files'][0]['path'])
        def vector(key):
            frame = gpd.read_file(path(key))
            if not frame.crs or frame.empty or not frame.geometry.is_valid.all():
                raise ValueError(f"Invalid vector input: {key}")
            return frame.to_crs(crs)
        boundary = vector('region_boundary').geometry.union_all()
        localities = vector('communities')
        if not localities.geom_type.eq('Point').all() or localities.id.duplicated().any() or not localities.geometry.covered_by(boundary).all():
            raise ValueError("Localities require unique IDs and points inside region")
        graph = ox.load_graphml(path('road_graph'))
        if not graph or not graph.number_of_edges() or CRS(graph.graph.get('crs')) != crs:
            raise ValueError("Road graph must be nonempty in the configured metric CRS")
        native = repository_path(root, inputs['population']['native_source_subset']['path'])
        population = Population.load(native, crs, inputs['population']['native_source_subset']['path'], rounding,
                                     inputs['population']['source_spatial_resolution'])
        return cls(bundle, digest(bundle_path), crs, boundary, vector('hydrography'), localities, graph, population, path('dem'))


def severity(flooded, distance, access, exposed, warning_distance):
    if access == 'isolated':
        return 'critical', ['Baseline access lost under assumed at-grade closures.']
    if flooded is True or access == 'at_risk_of_isolation':
        return 'high', ['Locality point intersects assumed flood or access depends on uncertain roads.']
    if flooded is None or access == 'unknown':
        return 'unknown', ['Insufficient flood coverage or baseline network access information.']
    if access == 'degraded_access' or (distance is not None and distance <= warning_distance) or (exposed or 0) > 0:
        return 'warning', ['Nearby buffer exposure, flood proximity, or local road disruption under the scenario.']
    return 'safe', ['No configured impact trigger; safe means within this scenario only, not verified safety.']


def analyze(region, scenario, root, run_id):
    spec, thresholds = scenario.flood, scenario.thresholds
    if spec.method == 'connected_terrain':
        flood = terrain_extent(region.dem_path, region.hydrography, region.boundary, region.crs, spec)
    else:
        flood = load_extent(repository_path(root, spec.path), region.boundary, region.crs, spec.source, spec.assumption)
    records, geometries, closed, uncertain, road_tree = evaluate_roads(region.graph, flood.geometry, flood.known_area, thresholds)
    connectivity = Connectivity(region.graph, region.boundary, flood.geometry, flood.known_area, closed, uncertain, thresholds)
    locality_features = []
    for _, row in region.localities.sort_values('id').iterrows():
        point = row.geometry
        buffer = point.buffer(thresholds.locality_buffer_m).intersection(region.boundary)
        exposed = region.population.exposure(buffer.intersection(flood.geometry))
        distance = point.distance(flood.geometry) if not flood.geometry.is_empty else None
        flooded = flood.geometry.covers(point) if flood.known_area.covers(point) else None
        neighbourhood = [records[i] for i in road_tree.query(buffer, predicate='intersects')]
        nearby = [record for record in neighbourhood if record['status'] in {'closure_candidate', 'uncertain_structure', 'near_flood'}]
        access = connectivity.locality(point, bool(nearby))
        level, reasons = severity(flooded, distance, access['accessibility'], exposed['exposed_population'], thresholds.warning_distance_m)
        props = {"locality_id": row.id, "name": row['name'], "representation": "representative_point_with_assumed_buffer",
                 "flooded": flooded, "flood_distance_m": round(distance, 1) if distance is not None else None,
                 "approximate_population_exposure": exposed, "buffer_radius_m": thresholds.locality_buffer_m,
                 "buffer_flood_known_coverage_fraction": round(buffer.intersection(flood.known_area).area / buffer.area,6),
                 "nearby_affected_directed_edges": len(nearby), "flood_severity": level,
                 "nearby_unknown_directed_edges": sum(record['status'] == 'unknown' for record in neighbourhood),
                 "reasons": reasons, "source": flood.source, **access}
        locality_features.append(feature(point, props, region.crs))
    props = [f['properties'] for f in locality_features]
    assumptions = flood.reasons + [
        "Locality buffers are overlapping analysis neighbourhoods, not administrative areas; never sum their population estimates.",
        "Gateways are clear nodes in the inside boundary ring of the largest baseline weak component; not verified destinations.",
        "Localities snap once to the nearest baseline node within configured limit; connector passability is not surveyed.",
        "Optimistic graph removes at-grade closure candidates; cautious graph also removes uncertain structures and outside-coverage edges.",
        "Pre-existing disconnection, absent gateways or excessive snapping distance yield unknown, not flood-caused isolation.",
        "All road counts are directed edges, including opposite directions; not unique physical roads."]
    summary = {"run_id": run_id, "region_id": region.bundle['region_id'], "scenario_id": scenario.scenario_id,
        "stage": scenario.stage, "replay_at": scenario.replay_at.isoformat(), "timestamp_meaning": scenario.timestamp_meaning,
        "is_demo": False, "operationally_validated": False, "source": flood.source,
        "algorithm_version": ALGORITHM_VERSION, "bundle_sha256": region.bundle_hash,
        "scenario": scenario.model_dump(mode='json'), "flooded_area_km2": round(flood.geometry.area / 1e6, 4),
        "flood_known_coverage_fraction": round(flood.known_area.area / region.boundary.area,6),
        "population": region.population.exposure(flood.geometry),
        "locality_counts": dict(Counter(p['flood_severity'] for p in props)),
        "locality_exposure_counts": {"total": len(props), "flooded_points": sum(p['flooded'] is True for p in props),
            "unknown_points": sum(p['flooded'] is None for p in props),
            "buffers_with_estimated_exposure": sum((p['approximate_population_exposure']['exposed_population'] or 0) > 0 for p in props)},
        "accessibility_counts": dict(Counter(p['accessibility'] for p in props)),
        "road_counts": dict(Counter(p['status'] for p in records)), "road_count_unit": "directed_graph_edges",
        "gateway_count": len(connectivity.gateways), "assumptions": assumptions,
        "limitations": scenario.evidence_limitations + ["Scenario consequences are not operational evacuation advice.",
            "Only one assumed stage; no inferred arrival times, forecast stages, shelters, evacuation routes or exit deadlines.",
            "DSM contains buildings/vegetation; river channel water is included, and levees/decks/bathymetry are unresolved.",
            region.population.resolution_note,
            "Known flood coverage and known population coverage are separate; uncovered areas remain unknown.",
            "Historical OSM includes pre-existing disconnected components, uncertain access and no turn restrictions."]}
    roads = [feature(geom, {**record, 'source': flood.source}, region.crs)
             for record, geom in zip(records, geometries) if record['status'] != 'unaffected']
    return {'summary': summary, 'localities': collection(locality_features), 'road-impacts': collection(roads),
            'flood': collection([] if flood.geometry.is_empty else [feature(flood.geometry, {
                'source': flood.source, 'stage': scenario.stage, 'replay_at': scenario.replay_at.isoformat(),
                'assumptions': flood.reasons}, region.crs)])}
