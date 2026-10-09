import hashlib
import json
import os
from pathlib import Path
from threading import Lock

from fastapi import HTTPException
from app.schemas.evacuation import EvacuationResult, PlanningConfig
from app.schemas.consequences import Scenario
from app.services import consequences

CONFIG=Path(os.getenv('EVACUATION_CONFIG',consequences.ROOT/'config/phase4-pilot.json'))
CACHE=consequences.REPOSITORY/'artifacts/evacuation'
LOCK=Lock()


def load_config():
    return PlanningConfig.model_validate_json(CONFIG.read_text())


def inputs(run_id):
    # Read and fingerprint saved Phase 3 outputs; never call analyze/create_run.
    layers={key:consequences.read_run(run_id,key) for key in ('summary','localities','road-impacts','flood')}
    hashes={key:hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest() for key,value in layers.items()}
    return layers,hashes


def compute(layers,config):
    import geopandas as gpd
    import numpy as np
    import rasterio
    from shapely.geometry import shape
    from shapely.ops import unary_union
    from app.geospatial.consequences import digest, repository_path
    from app.geospatial.flood import polygonize
    from app.geospatial.spatial import project
    from app.evacuation.planning import plan_all
    summary=layers['summary'];scenario=Scenario.model_validate(summary['scenario'])
    root=consequences.REPOSITORY
    bundle_path=repository_path(root,scenario.bundle)
    if digest(bundle_path)!=summary['bundle_sha256']: raise ValueError('Bundle differs from the Phase 3 run')
    region=consequences.region_data(str(bundle_path),summary['bundle_sha256'],scenario.thresholds.population_rounding_people)
    source=region.bundle['inputs']['safe_site_candidates']['files'][0]
    sites=gpd.read_file(repository_path(root,source['path']))
    if not sites.crs or sites['id'].duplicated().any(): raise ValueError('Sites require a CRS and unique IDs')
    sites=sites.to_crs(region.crs)
    flood=unary_union([project(shape(f['geometry']),'EPSG:4326',region.crs) for f in layers['flood']['features']])
    # Coverage only: no water-surface propagation or exposure recomputation.
    coverage_path=region.dem_path if scenario.flood.method=='connected_terrain' else repository_path(root,scenario.flood.path)
    if coverage_path.suffix.lower() in {'.tif','.tiff'}:
        with rasterio.open(coverage_path) as src:
            data=src.read(1,masked=True);valid=~np.ma.getmaskarray(data)&np.isfinite(data.data)
            known=project(polygonize(valid,src.transform),src.crs,region.crs).intersection(region.boundary)
    else: known=region.boundary
    impacts={f['properties']['edge_id']:f['properties'] for f in layers['road-impacts']['features']}
    return plan_all(region.graph,sites,flood,known,layers['localities'],impacts,summary,config,region.crs)


def get_evacuation(run_id):
    try:
        from app.evacuation.planning import VERSION
        layers,hashes=inputs(run_id)
        config=load_config()
        key=json.dumps([VERSION,hashes,config.model_dump(mode='json')],sort_keys=True)
        planning_id='evacuation-'+hashlib.sha256(key.encode()).hexdigest()[:24]
        path=CACHE/f'{planning_id}.json'
        with LOCK:
            if path.exists(): return EvacuationResult.model_validate_json(path.read_text()).model_dump(mode='json')
            result={**compute(layers,config),'run_id':run_id,'planning_id':planning_id,'algorithm_version':VERSION,
                    'configuration':config.model_dump(mode='json'),'operationally_validated':False,
                    'provenance':{'consequence_output_hashes':hashes,'bundle_sha256':layers['summary']['bundle_sha256'],
                                  'replay_at':layers['summary']['replay_at'],'flood_source':layers['summary']['source'],
                                  'phase3_assumptions':layers['summary']['assumptions'],'phase3_limitations':layers['summary']['limitations']}}
            result=EvacuationResult.model_validate(result).model_dump(mode='json')
            CACHE.mkdir(parents=True,exist_ok=True)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w',dir=CACHE,delete=False,suffix='.tmp') as stream:
                temporary=Path(stream.name)
                json.dump(result,stream,sort_keys=True,allow_nan=False)
            try: temporary.replace(path)
            finally: temporary.unlink(missing_ok=True)
            return result
    except ImportError as exc:
        raise HTTPException(503,{'code':'PLANNING_DEPENDENCIES_MISSING','message':'Install backend geospatial dependencies.'}) from exc
    except (OSError,ValueError,KeyError) as exc:
        raise HTTPException(409,{'code':'PLANNING_INPUT_INVALID','message':str(exc)}) from exc
