"""Validate local inputs and publish a small, standardized bundle index.

No network access. A failed check exits nonzero and removes any stale bundle
index, while preserving all raw and processed datasets for investigation.
"""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'preprocessing'))
from common import CATALOG, CONFIG_PATH, PROCESSED, ROOT, config, file_record, read_json, sha256, write_json
from prepare import grid_for, study_geometry
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import CRS
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import mapping, shape


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_vector(path, boundary, metric_crs, points=False, inside=False):
    data = read_json(path)
    require(data['type'] == 'FeatureCollection' and data['features'], f'Empty/non-GeoJSON collection: {path}')
    frame = gpd.read_file(path)
    require(frame.crs == CRS.from_epsg(4326), 'GeoJSON must be EPSG:4326, longitude then latitude')
    require(frame.geometry.notna().all() and (~frame.geometry.is_empty).all() and frame.geometry.is_valid.all(), 'Invalid or empty geometry')
    require(frame['id'].notna().all() and frame['id'].is_unique, 'IDs must be present and unique within a layer')
    minx, miny, maxx, maxy = frame.total_bounds
    require(-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90, 'Invalid WGS84 coordinates')
    projected = frame.to_crs(metric_crs)
    require(projected.intersects(boundary).all(), 'Every feature must intersect the pilot')
    if inside:
        require(projected.within(boundary.buffer(.01)).all(), 'Feature outside pilot boundary')
    if points:
        require((frame.geom_type == 'Point').all(), 'Expected representative points')
        require(np.allclose(frame.longitude, frame.geometry.x, atol=1e-10, rtol=0), 'Longitude fields do not match geometry')
        require(np.allclose(frame.latitude, frame.geometry.y, atol=1e-10, rtol=0), 'Latitude fields do not match geometry')
    return frame


def validate_raster(path, metadata, grid, boundary, kind):
    with rasterio.open(path) as src:
        require(src.crs == CRS.from_user_input(grid['crs']), 'Wrong raster CRS')
        require(src.transform.almost_equals(grid['transform']) and (src.height, src.width) == (grid['height'], grid['width']), 'Raster does not match shared grid')
        require(list(src.bounds) == metadata['bounds'] and list(src.res) == metadata['resolution'], 'Raster bounds/resolution metadata differ')
        require(str(src.crs) == metadata['crs'] and src.nodata == metadata['nodata'], 'Raster CRS/nodata metadata differ')
        require(bool(src.tags().get('resampling')), 'Resampling method must be documented')
        mask = geometry_mask([mapping(boundary)], (src.height, src.width), src.transform, invert=True)
        if kind == 'evidence':
            require(src.count == 4 and src.colorinterp[-1] == rasterio.enums.ColorInterp.alpha, 'Evidence must have RGB and alpha')
            valid = src.read(4) > 0
            require(valid.any() and not (valid & ~mask).any(), 'Evidence alpha outside pilot or empty')
            return {'visible_pixels': int(valid.sum()), 'classified_flood_mask': False}
        data = src.read(1, masked=True)
        values = data.compressed()
        require(len(values) > 0 and np.isfinite(values).all(), 'No finite valid raster values')
        if kind == 'population':
            require((values >= 0).all() and values.sum() > 0, 'Population counts must be nonnegative and nonempty')
            require(src.tags().get('units') == 'persons per grid cell within study boundary', 'Population output must be counts')
        elif kind == 'dem':
            require(src.tags().get('units') == 'metres', 'DEM units must be metres')
            require(not ((~np.ma.getmaskarray(data)) & ~mask).any(), 'DEM has values outside pilot mask')
        return {'valid_pixels': len(values), 'minimum': float(values.min()), 'maximum': float(values.max()),
                **({'population_total': float(values.sum())} if kind == 'population' else {})}


def validate_manifests(manifests, pilot):
    count, files = 0, {}
    required = {'id', 'name', 'provider', 'url', 'license', 'original_crs', 'processed_crs',
                'spatial_resolution', 'temporal_coverage', 'raw_files', 'processed_files', 'preprocessing_steps', 'limitations'}
    for dataset_id, manifest in manifests.items():
        require(required <= manifest.keys(), f'{dataset_id}: missing manifest fields {required - manifest.keys()}')
        require(manifest['id'] == dataset_id, 'Manifest identifier mismatch')
        require(manifest['configuration_sha256'] == sha256(CONFIG_PATH), f'{dataset_id}: processed with a different configuration')
        require(manifest['processed_files'] and manifest['preprocessing_steps'], f'{dataset_id}: not processed')
        if dataset_id != 'region':
            require(manifest.get('acquired_at') and manifest['raw_files'], f'{dataset_id}: acquisition provenance missing')
        for record in manifest['raw_files'] + manifest['processed_files']:
            path = ROOT / record['path']
            require(path.is_file(), f'Missing file: {record["path"]}')
            if path not in files:
                files[path] = (path.stat().st_size, sha256(path))
            require(files[path] == (record['bytes'], record['sha256']), f'Checksum/size mismatch: {path}')
            count += 1
        if dataset_id.startswith('osm_'):
            require(manifest['temporal_coverage'] == pilot['osm_snapshot_at'], 'Wrong OSM snapshot')
            require(f'[date:"{pilot["osm_snapshot_at"]}"]' in manifest['query'], 'Historical query date absent')
            query_path = CATALOG / 'queries' / f'{dataset_id}.overpassql'
            require(query_path.read_text().strip() == manifest['query'].strip(), 'Saved query differs from successful acquisition')
            elements = ET.parse(ROOT / manifest['raw_files'][0]['path']).getroot()
            require(elements.find('remark') is None, 'Overpass returned an error')
            require(all(item.get('timestamp', '') <= pilot['osm_snapshot_at'] for item in elements if item.tag in ('node', 'way', 'relation')), 'OSM contains edits after snapshot')
    return {'datasets': len(manifests), 'unique_files_checksum_verified': len(files), 'file_references': count}


def main():
    pilot = config()
    wgs, metric = study_geometry(pilot)
    sources = read_json(CATALOG / 'sources.json')
    dem_id = next(key for key, value in sources.items() if value['category'] == 'elevation')
    pop_id = next(key for key, value in sources.items() if value['category'] == 'population')
    flood_ids = [key for key, value in sources.items() if value['category'] == 'flood']
    expected_ids = ['region', dem_id, pop_id, 'osm_roads', 'osm_hydrography', 'osm_communities', 'osm_safe_sites', *pilot['gauge']['source_ids'], *flood_ids]
    checks, manifests = [], {}

    def run(name, function):
        try:
            details = function()
            checks.append({'name': name, 'status': 'pass', 'details': details})
        except Exception as error:
            checks.append({'name': name, 'status': 'fail', 'error': str(error)})

    def inventory():
        missing = []
        for key in expected_ids:
            path = CATALOG / f'manifests/{key}.json'
            if path.exists():
                manifests[key] = read_json(path)
            else:
                missing.append(key)
        require(not missing, f'Missing manifests: {missing}')
        for key, source in sources.items():
            require(manifests[key]['url'] == source['url'], f'{key}: source catalogue URL differs from cached acquisition')
        return validate_manifests(manifests, pilot)

    run('provenance_and_checksums', inventory)
    dem_grid = grid_for(pilot, metric, pilot['dem_resolution_m'])
    pop_grid = grid_for(pilot, metric, pilot['population_resolution_m'])
    dem_path = PROCESSED / f'elevation/dem_{pilot["dem_resolution_m"]}m.tif'
    pop_path = PROCESSED / f'population/population_{pilot["population_resolution_m"]}m.tif'

    def boundary_check():
        frame = validate_vector(PROCESSED / 'region/boundary.geojson', metric, pilot['metric_crs'])
        require(shape(read_json(PROCESSED / 'region/boundary.geojson')['features'][0]['geometry']).equals(wgs), 'Boundary changed from configuration')
        require(abs(frame.iloc[0].area_km2 - metric.area / 1e6) < 1e-9, 'Boundary area metadata differs')
        return {'bbox_wgs84': pilot['bbox_wgs84'], 'area_km2': metric.area / 1e6, 'metric_crs': pilot['metric_crs']}
    run('pilot_boundary', boundary_check)
    run('dem', lambda: validate_raster(dem_path, manifests[dem_id]['raster'], dem_grid, metric, 'dem'))

    def population_check():
        result = validate_raster(pop_path, manifests[pop_id]['rasters'][0], pop_grid, metric, 'population')
        totals = manifests[pop_id]['conservation']
        require(np.isclose(totals['source_fractional_pilot_total'], result['population_total'], rtol=1e-9, atol=1e-6), 'Population counts not conserved')
        require(totals['source_nodata_reinterpreted_as_zero'] is False, 'Unknown population must stay unknown')
        with rasterio.open(PROCESSED / f'population/known_coverage_fraction_{pilot["population_resolution_m"]}m.tif') as src:
            coverage = src.read(1)
            require(src.crs == CRS.from_user_input(pilot['metric_crs']) and src.transform == pop_grid['transform'], 'Wrong coverage grid')
            require(np.isfinite(coverage).all() and coverage.min() >= 0 and coverage.max() <= 1, 'Invalid coverage fractions')
            result['partially_known_cells'] = int(((coverage > 0) & (coverage < .999999)).sum())
        require(dem_grid['bounds'] == pop_grid['bounds'], 'DEM/population grids not nested')
        return {**result, **totals}
    run('population_conservation_and_alignment', population_check)

    def graph_check():
        graph = ox.load_graphml(PROCESSED / 'roads/roads.graphml')
        require(graph.number_of_nodes() > 0 and graph.number_of_edges() > 0, 'Empty road graph')
        require(CRS.from_user_input(graph.graph['crs']) == CRS.from_user_input(pilot['metric_crs']), 'Road graph not metric')
        require(graph.graph['snapshot_at'] == pilot['osm_snapshot_at'], 'Road graph snapshot mismatch')
        nodes, edges = ox.graph_to_gdfs(graph)
        require(nodes.within(metric.buffer(pilot['road_buffer_m'] + .1)).all() and nodes.intersects(metric).any(), 'Road buffer/intersection wrong')
        require(edges.geometry.is_valid.all() and (~edges.geometry.is_empty).all(), 'Invalid edge geometry')
        require(np.allclose(edges['length'], edges.length, atol=1e-6, rtol=1e-9), 'Road lengths not projected metres')
        require((edges.speed_kph > 0).all() and np.isfinite(edges.travel_time).all(), 'Invalid speeds/travel times')
        require(np.allclose(edges.travel_time, edges['length'] / (edges.speed_kph / 3.6)), 'Travel-time units inconsistent')
        require(set(edges.speed_source) <= {'osm_maxspeed_tag', 'configured_class_assumption'}, 'Unlabelled speed assumption')
        require((edges.travel_time_status == 'free_flow_estimate_not_flood_evacuation_time').all(), 'Road times mislabeled')
        require(len(gpd.read_file(PROCESSED / 'roads/roads.gpkg', layer='edges')) == len(edges), 'GPKG edge count differs')
        stats = {'nodes': len(nodes), 'edges': len(edges), 'weak_components': nx.number_weakly_connected_components(graph),
                 'assumed_speed_edges': int((edges.speed_source == 'configured_class_assumption').sum())}
        require(stats == manifests['osm_roads']['graph_statistics'], 'Graph statistics metadata differs')
        return stats
    run('persisted_road_graph', graph_check)

    def point_check(category, filename):
        frame = validate_vector(PROCESSED / category / filename, metric, pilot['metric_crs'], points=True, inside=True)
        require((frame.snapshot_at == pilot['osm_snapshot_at']).all(), 'Feature timestamp differs')
        require(frame['id'].str.startswith('osm/').all(), 'Not real OSM element identities')
        require(not frame['name'].fillna('').str.fullmatch(r'Zone\s+\d+', case=False).any(), 'Synthetic UI labels entered data')
        if category == 'safe_sites':
            require((frame.verification_status == 'unverified_candidate').all() and (~frame.safety_assessed).all(), 'Unverified facilities mislabeled safe')
            require(frame.capacity.isna().all() and frame.capacity_source.isna().all(), 'Invented facility capacity')
        else:
            require((~frame.is_administrative_boundary).all() and frame.population.isna().all(), 'Invented locality boundaries/populations')
        names = frame['name'].dropna().str.casefold().value_counts()
        return {'features': len(frame), 'representation': sorted(frame.representation.unique().tolist()),
                'unnamed_features': int(frame['name'].isna().sum()),
                'repeated_name_groups': int((names > 1).sum()),
                'physical_entities_deduplicated': False}
    run('communities', lambda: point_check('communities', 'localities.geojson'))
    run('candidate_sites', lambda: point_check('safe_sites', 'candidates.geojson'))
    run('hydrography', lambda: {'features': len(validate_vector(PROCESSED / 'hydrography/hydrography.geojson', metric, pilot['metric_crs']))})

    def gauge_check():
        frame = validate_vector(PROCESSED / 'gauge/station.geojson', metric, pilot['metric_crs'], points=True, inside=True)
        observations = read_json(PROCESSED / 'gauge/observations.json')
        require(len(observations['observations']) == 1 and observations['interpolated'] is False, 'Gauge time series fabricated')
        value = observations['observations'][0]
        require(value['at'] == pilot['gauge']['peak_at'] and value['level_m'] == pilot['gauge']['peak_level_m'], 'Reference transcription mismatch')
        require(frame.iloc[0].danger_level_m == pilot['gauge']['danger_level_m'], 'Gauge threshold differs')
        return {'stations': len(frame), 'documented_observations': 1, 'vertical_datum_reconciled': False}
    run('gauge_reference', gauge_check)

    def flood_check():
        coverage = validate_vector(PROCESSED / 'flood/evidence_coverage.geojson', metric, pilot['metric_crs'])
        require((coverage.representation == 'map_coverage_not_flood_extent').all(), 'Map coverage mislabeled flood extent')
        results = {}
        for key in flood_ids:
            manifest = manifests[key]
            require(manifest['quantitative_flood_mask'] is False, 'Cartographic imagery mislabeled classified flood')
            require(manifest['max_control_fit_residual_m'] < 5, 'Poor control-point fit')
            results[key] = validate_raster(ROOT / manifest['raster']['path'], manifest['raster'], dem_grid, metric, 'evidence')
        results['map_coverage_fraction_of_pilot'] = float(coverage.to_crs(pilot['metric_crs']).union_all().intersection(metric).area / metric.area)
        return results
    run('historical_flood_evidence', flood_check)

    warnings = list(pilot['limitations']) + sources[pop_id]['limitations'] + [
        'Hydrography includes mapped waterway ways only; natural=water features and multipolygon relations are omitted.',
        'Localities are mapped place nodes only; candidate facilities are mapped nodes/ways only. Relations are omitted.',
        'NRSC/CWC public access does not establish an open redistribution licence; NRSC maps are marked For official use.',
        'NRSC map coverage is partial, with clouds/labels; Shastri Park map date and identifier disagree.',
        'GeoPDF control fit measures internal registration only, not independent positional accuracy.',
        'Road graph has disconnected components and omits turn restrictions/conditional access; no flood isolation inference is made.',
    ]
    passed = all(check['status'] == 'pass' for check in checks)
    report = {'schema_version': '1.0', 'region_id': pilot['id'], 'status': 'pass' if passed else 'fail',
              'configuration_sha256': sha256(CONFIG_PATH), 'checks': checks, 'warnings': warnings,
              'scope': 'Dataset integrity and declared representation only; not operational flood/evacuation validation'}
    write_json(CATALOG / 'validation/report.json', report)
    lines = [f'# Dataset validation — {pilot["id"]}', '', f'**Status: {report["status"].upper()}**', '', report['scope'], '', '| Check | Result | Evidence |', '| --- | --- | --- |']
    for check in checks:
        details = json.dumps(check.get('details', check.get('error')), ensure_ascii=False).replace('|', '/')
        lines.append(f'| {check["name"]} | {check["status"]} | {details} |')
    lines.extend(['', '## Limitations', '', *[f'- {warning}' for warning in warnings], ''])
    (CATALOG / 'validation/report.md').write_text('\n'.join(lines))

    bundle_path = CATALOG / 'bundle.json'
    if passed:
        inventory = {}
        for key, manifest in manifests.items():
            for role in ('raw_files', 'processed_files'):
                for record in manifest[role]:
                    row = inventory.setdefault(record['path'], {'record': record, 'manifests': [], 'role': role})
                    row['manifests'].append(key)
        inventory_lines = ['# Validated file inventory', '', 'Generated by `scripts/validation/validate_dataset.py`. Paths are relative to the repository root. All dataset files listed here are ignored by Git; checksums live in their manifests.', '', '| File | Bytes | Manifest(s) |', '| --- | ---: | --- |']
        for path, row in sorted(inventory.items()):
            inventory_lines.append(f'| `{path}` | {row["record"]["bytes"]:,} | {", ".join(row["manifests"])} |')
        (CATALOG / 'validation/inventory.md').write_text('\n'.join(inventory_lines) + '\n')
        def entry(ids, representation):
            files = {record['path']: record for key in ids for record in manifests[key]['processed_files']}
            return {'representation': representation, 'manifest_ids': ids, 'files': list(files.values())}
        bundle = {'schema_version': '1.0', 'region_id': pilot['id'], 'region_version': pilot['version'],
                  'bbox_wgs84': pilot['bbox_wgs84'], 'metric_crs': pilot['metric_crs'], 'web_crs': pilot['web_crs'],
                  'configuration': file_record(CONFIG_PATH), 'source_catalogue': file_record(CATALOG / 'sources.json'),
                  'toolchain_lock': file_record(ROOT / 'scripts/requirements-lock.txt'),
                  'validation_report': file_record(CATALOG / 'validation/report.json'),
                  'readiness': {'dataset_integrity_validated': True, 'quantitative_flood_mask_available': False,
                                'gauge_dem_vertical_datums_reconciled': False, 'operational_use_validated': False},
                  'inputs': {
                      'region_boundary': entry(['region'], 'analysis_rectangle'),
                      'gauge': entry(pilot['gauge']['source_ids'], 'catalogued_station_and_documented_peak_only'),
                      'dem': entry([dem_id], 'surface_elevation_raster'),
                      'population': entry([pop_id], 'estimated_person_counts_and_known_coverage'),
                      'road_graph': entry(['osm_roads'], 'historical_directed_motor_vehicle_graph'),
                      'hydrography': entry(['osm_hydrography'], 'mapped_water_geometries'),
                      'communities': entry(['osm_communities'], 'locality_representative_points'),
                      'safe_site_candidates': entry(['osm_safe_sites'], 'unverified_facilities_unknown_capacity'),
                      'historical_flood_evidence': entry(flood_ids, 'georeferenced_cartographic_satellite_evidence'),
                  }}
        bundle['inputs']['population'].update(
            native_source_subset=manifests[pop_id]['raw_files'][0],
            source_spatial_resolution=manifests[pop_id]['spatial_resolution'],
            native_resolution_m_nominal=manifests[pop_id].get('native_resolution_m_nominal'),
            aligned_grid_resolution_m=pilot['population_resolution_m'],
            fine_grid_is_alignment_only=True,
            within_native_cell_assumption='Uniform population per projected area; no inferred subpixel distribution')
        write_json(bundle_path, bundle)
    else:
        bundle_path.unlink(missing_ok=True)
        (CATALOG / 'validation/inventory.md').unlink(missing_ok=True)
    print(json.dumps({'status': report['status'], 'checks': len(checks), 'failed': [c for c in checks if c['status'] == 'fail']}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
