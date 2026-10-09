"""Offline pilot regression; preserves every Phase 3 output and report."""
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote
from fastapi.testclient import TestClient
from shapely.geometry import shape
from app.main import app
from app.schemas.evacuation import EvacuationResult
from app.services import consequences
from app.services.evacuation import get_evacuation, inputs, compute, load_config
from .routing import physical_pair


def main():
    root=consequences.REPOSITORY
    phase3=json.loads((root/'docs/phase-3-results.json').read_text())
    run=phase3['summary']['run_id']
    expected=phase3['output_checksums']
    def preserved():
        for layer,checksum in expected.items():
            path=consequences.CACHE/run/f'{layer}.json'
            assert hashlib.sha256(path.read_bytes()).hexdigest()==checksum,layer
    preserved()
    started=time.monotonic();result=get_evacuation(run);initial=time.monotonic()-started
    started=time.monotonic();assert get_evacuation(run)==result;cached=time.monotonic()-started
    layers,hashes=inputs(run)
    started=time.monotonic();independent=compute(layers,load_config());compute_seconds=time.monotonic()-started
    validated=EvacuationResult.model_validate({**result,**independent}).model_dump(mode='json')
    assert validated==result,'Independent planning differs from persisted output'
    excluded={f['properties']['edge_id'] for f in layers['road-impacts']['features']
              if f['properties']['status'] in result['configuration']['excluded_road_statuses']}
    for plan in result['plans']:
        for kind in ('primary_route','backup_route'):
            route=plan[kind]
            if route:
                assert not excluded.intersection(route['edge_ids'])
                geometry=shape(route['geometry']['geometry'])
                assert geometry.is_valid and geometry.geom_type=='LineString'
                west,south,east,north=geometry.bounds
                assert -180<=west<=east<=180 and -90<=south<=north<=90
        if plan['backup_route']:
            pairs=lambda route:{physical_pair(*edge.split(':')[:2]) for edge in route['edge_ids']}
            assert not pairs(plan['primary_route'])&pairs(plan['backup_route'])
        assert plan['demand_people'] is None
        assert plan['deadline']['latest_departure'] is None
    client=TestClient(app)
    for suffix in ('evacuation','safe-sites'):
        response=client.get(f'/api/v1/runs/{run}/{suffix}');assert response.status_code==200,response.text[:200]
    for plan in result['plans']:
        locality_id=quote(plan['locality']['locality_id'],safe='')
        response=client.get(f'/api/v1/runs/{run}/localities/{locality_id}/plan')
        assert response.status_code==200 and response.json()==plan
    preserved()
    report={'run_id':run,'planning_id':result['planning_id'],'algorithm_version':result['algorithm_version'],
            'counts':result['counts'],'configuration':result['configuration'],
            'timing_seconds':{'initial_request_including_cache_check':round(initial,3),'cached_request':round(cached,3),
                              'independent_compute':round(compute_seconds,3)},
            'checks':{'independent_recomputation_identical':True,'phase3_output_checksums_unchanged':True,
                      'all_planning_api_views_passed':True,'excluded_edges_absent':True,'backups_network_link_disjoint':True,
                      'web_route_geometry_valid':True,'unknown_demands_and_deadlines_preserved':True},
            'provenance':result['provenance'],'plans':[]}
    for p in result['plans']:
        destination=p['selected_destination']
        report['plans'].append({'id':p['locality']['locality_id'],'name':p['locality']['name'],
            'destination':destination['properties'] if destination else None,
            'demand_people':p['demand_people'],'capacity_status':p['capacity_status'],'priority':p['priority'],
            'distance_km':p['primary_route']['distance_km'] if p['primary_route'] else None,
            'travel_minutes':p['primary_route']['travel_minutes'] if p['primary_route'] else None,
            'backup_status':p['backup_status'],'backup_travel_minutes':p['backup_route']['travel_minutes'] if p['backup_route'] else None,
            'deadline':p['deadline'],'outcomes':p['outcomes']})
    (root/'docs/phase-4-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'counts':result['counts'],'checks':report['checks'],'timing':report['timing_seconds']},indent=2))


if __name__=='__main__': main()
