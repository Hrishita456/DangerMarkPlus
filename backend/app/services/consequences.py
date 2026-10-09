"""Local, content-addressed runs. No database, workers or arbitrary client paths."""
import hashlib
import json
import os
import re
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from threading import Lock

from fastapi import HTTPException
from app.schemas.consequences import ConsequenceSummary, GeoCollection, Scenario

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(os.getenv('CONSEQUENCE_SCENARIO_CONFIG', ROOT / 'config/phase3-pilot.json'))
# ROOT above is backend/; datasets and artifacts live one level above.
REPOSITORY = ROOT.parent
CACHE = REPOSITORY / 'artifacts/consequences'
RUN_LOCK = Lock()


def config():
    return Scenario.model_validate_json(CONFIG.read_text())


@lru_cache(maxsize=2)
def region_data(bundle_path, bundle_hash, rounding):
    from app.geospatial.consequences import Region
    return Region.load(REPOSITORY, Path(bundle_path), rounding)


def create_run(scenario_id):
    try:
        scenario = config()
        if scenario.scenario_id != scenario_id:
            raise HTTPException(404, {'code': 'SCENARIO_NOT_FOUND', 'message': 'Scenario is not configured on this server.'})
        from app.geospatial.consequences import ALGORITHM_VERSION, analyze, digest, repository_path
        bundle_path = repository_path(REPOSITORY, scenario.bundle)
        bundle_hash = digest(bundle_path)
        extent_hash = digest(repository_path(REPOSITORY, scenario.flood.path)) if scenario.flood.path else None
        key = json.dumps([ALGORITHM_VERSION, bundle_hash, extent_hash, scenario.model_dump(mode='json')], sort_keys=True)
        run_id = 'analysis-' + hashlib.sha256(key.encode()).hexdigest()[:24]
        with RUN_LOCK:
            # Validate inputs once per process even when reusing persisted results.
            region = region_data(str(bundle_path), bundle_hash, scenario.thresholds.population_rounding_people)
            destination = CACHE / run_id
            cached = destination.is_dir()
            if not cached:
                outputs = analyze(region, scenario, REPOSITORY, run_id)
                outputs['summary'] = ConsequenceSummary.model_validate(outputs['summary']).model_dump(mode='json')
                for layer in ('flood','localities','road-impacts'):
                    GeoCollection.model_validate(outputs[layer])
                CACHE.mkdir(parents=True, exist_ok=True)
                temporary = Path(tempfile.mkdtemp(prefix='.run-', dir=CACHE))
                try:
                    for name, payload in outputs.items():
                        (temporary / f'{name}.json').write_text(json.dumps(payload, sort_keys=True, allow_nan=False))
                    # Other processes may have finished the same deterministic run.
                    try:
                        temporary.rename(destination)
                    except OSError:
                        if not destination.is_dir():
                            raise
                finally:
                    if temporary.exists(): shutil.rmtree(temporary)
        return {'run_id': run_id, 'scenario_id': scenario_id,
                'summary_url': f'/api/v1/runs/{run_id}/summary', 'cached': cached}
    except ImportError as exc:
        raise HTTPException(503, {'code': 'ANALYSIS_DEPENDENCIES_MISSING', 'message': 'Install backend geospatial dependencies; replay remains available.'}) from exc
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(409, {'code': 'ANALYSIS_INPUT_INVALID', 'message': str(exc)}) from exc


def read_run(run_id, layer):
    if not re.fullmatch(r'analysis-[0-9a-f]{24}', run_id) or layer not in {'summary','localities','road-impacts','flood'}:
        raise HTTPException(404, {'code': 'RUN_NOT_FOUND', 'message': 'Computed run not found.'})
    path = CACHE / run_id / f'{layer}.json'
    if not path.is_file():
        raise HTTPException(404, {'code': 'RUN_NOT_FOUND', 'message': 'Computed run not found. Analyze a configured scenario first.'})
    return json.loads(path.read_text())
