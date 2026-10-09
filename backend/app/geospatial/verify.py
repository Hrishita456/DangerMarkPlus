"""Optional real-bundle regression. Offline, preserves every Phase 2 artifact."""
import hashlib
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from app.main import app
from app.services.consequences import CACHE, REPOSITORY, config, create_run, read_run, region_data
from .consequences import analyze, digest


def main():
    scenario = config()
    start = time.monotonic()
    result = create_run(scenario.scenario_id)
    first = time.monotonic() - start
    print(f"Run available: {result['run_id']}", flush=True)
    start = time.monotonic()
    repeated = create_run(scenario.scenario_id)
    warm = time.monotonic() - start
    assert repeated['run_id'] == result['run_id'] and repeated['cached']
    layers = ['summary', 'localities', 'road-impacts', 'flood']
    client = TestClient(app)
    api_seconds = {}
    for layer in layers:
        start = time.monotonic()
        response = client.get(f"/api/v1/runs/{result['run_id']}/{layer}")
        assert response.status_code == 200, (layer, response.text[:200])
        api_seconds[layer] = round(time.monotonic() - start, 3)
    print('All four API read endpoints passed.', flush=True)
    bundle = REPOSITORY / scenario.bundle
    region = region_data(str(bundle), digest(bundle), scenario.thresholds.population_rounding_people)
    outputs = analyze(region, scenario, REPOSITORY, result['run_id'])
    for layer, payload in outputs.items():
        # GeoJSON tuples serialize as arrays: compare the actual JSON representation.
        assert json.loads(json.dumps(payload)) == read_run(result['run_id'], layer), layer
    summary = read_run(result['run_id'], 'summary')
    localities = read_run(result['run_id'], 'localities')['features']
    report = {
        'summary': summary,
        'timing_seconds': {'initial_request': round(first, 3), 'initial_was_cached': result['cached'],
                           'cached_request': round(warm, 3), 'read_api': api_seconds},
        'independent_recomputation_identical': True, 'api_layers_passed': layers,
        'whole_pilot_population_check': region.population.exposure(region.boundary),
        'affected_or_unknown_localities': [
            {key: f['properties'][key] for key in ('locality_id','name','flood_severity','accessibility',
                                                  'approximate_population_exposure')}
            for f in localities if f['properties']['flood_severity'] != 'safe'],
        'output_checksums': {layer: hashlib.sha256((CACHE / result['run_id'] / f'{layer}.json').read_bytes()).hexdigest()
                             for layer in layers}}
    output = REPOSITORY / 'docs/phase-3-results.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Independent recomputation identical. Report: {output}', flush=True)


if __name__ == '__main__':
    main()
