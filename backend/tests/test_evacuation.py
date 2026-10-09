import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
pytest.importorskip('rasterio',reason='Install geospatial extra for planning tests')
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, LineString, box, shape
from app.schemas.evacuation import PlanningConfig, EvacuationResult
from app.evacuation.routing import Network, physical_pair
from app.evacuation.assignment import assign, rank, capacity_status
from app.evacuation.deadlines import deadline
from app.evacuation.priority import score
from app.evacuation.planning import plan_all
from app.evacuation.sites import prepare_sites
from app.geospatial.spatial import feature, collection

CRS='EPSG:32643'
NOW='2023-07-13T12:00:00+05:30'


def config():
    return PlanningConfig.model_validate_json((Path(__file__).parents[1]/'config/phase4-pilot.json').read_text())


def graph(diamond=True):
    g=nx.MultiDiGraph(crs=CRS)
    for n,(x,y) in {0:(0,0),1:(100,50),2:(100,-50),3:(200,0),4:(400,0)}.items():
        g.add_node(n,x=720000+x,y=3170000+y)
    edges=[(0,1),(1,3)] + ([(0,2),(2,3)] if diamond else [])
    for u,v in edges:
        geom=LineString([(g.nodes[u]['x'],g.nodes[u]['y']),(g.nodes[v]['x'],g.nodes[v]['y'])])
        g.add_edge(u,v,length=geom.length,speed_kph=30,highway='residential',geometry=geom,name=f'Road {u}-{v}',osmid=100+u*10+v)
    return g


def point(g,n): return Point(g.nodes[n]['x'],g.nodes[n]['y'])


def context(g=None):
    g=g or graph();c=config();net=Network(g,{},c,CRS)
    flood=box(730000,3180000,730010,3180010);known=box(719000,3169000,722000,3171000)
    origin,_=net.attach(point(g,0),flood,known)
    dest,_=net.attach(point(g,3),flood,known)
    return g,c,net,flood,known,origin,dest


def locality(lid='osm/node/0'):
    return {'locality_id':lid,'name':'Test locality','flood_severity':'warning','accessibility':'degraded_access',
            'snapped_node_id':'0','approximate_population_exposure':{'exposed_population':2000}}


def site(identifier='site1',capacity=None):
    return {'properties':{'id':identifier,'verification_status':'unverified_candidate','capacity':capacity,
        'available_capacity':capacity,'assigned_locality_ids':[],'reserved_people':0},'geometry':Point(720200,3170000)}


def test_primary_backup_geometry_and_direction():
    g,c,net,flood,known,origin,dest=context()
    primary=net.route(origin,dest,NOW);backup=net.backup(origin,dest,primary,NOW)
    assert primary and backup and primary['distance_km']>0 and primary['travel_minutes']>0
    pairs=lambda r:{tuple(sorted(e.split(':')[:2])) for e in r['edge_ids']}
    assert not pairs(primary)&pairs(backup)
    geom=shape(primary['geometry']['geometry']);assert geom.is_valid
    assert 70<geom.bounds[0]<80 and 20<geom.bounds[1]<35
    assert net.route(dest,origin,NOW) is None
    assert primary['road_names'] and len(primary['connectors'])==2


def test_no_backup_and_unreachable():
    g,c,net,flood,known,origin,dest=context(graph(False))
    primary=net.route(origin,dest,NOW)
    assert primary and net.backup(origin,dest,primary,NOW) is None
    dest4={'node':4,'point':point(g,4),'node_point':point(g,4),'distance_m':0,'minutes':0}
    assert net.route(origin,dest4,NOW) is None


def test_unsafe_edge_exclusion_and_no_resnap():
    g=graph(False);c=config();net=Network(g,{'0:1:0':{'status':'closure_candidate'}},c,CRS)
    assert not net.graph.has_edge(0,1)
    a,reason=net.attach(point(g,0),box(730000,3180000,730010,3180010),box(719000,3169000,722000,3171000),preferred='0')
    assert a is None and 'no permitted' in reason


def test_access_connector_crossing_flood_rejected():
    g,c,net,flood,known,origin,dest=context()
    a,reason=net.attach(Point(719980,3170000),box(719985,3169999,719995,3170001),known,preferred='0')
    assert a is None and 'crosses flood' in reason


def test_parallel_edge_and_missing_speed():
    g=graph(False)
    g[0][1][0]['speed_kph']=None
    g.add_edge(0,1,key=1,**{**g[0][1][0],'speed_kph':60})
    g,c,net,flood,known,origin,dest=context(g)
    route=net.route(origin,dest,NOW)
    assert route['edge_ids'][0]=='0:1:1'
    assert net.graph[0][1][0]['speed_source']=='configured_class_default'
    # A faster parallel edge closes too early; slower open edge must remain usable.
    c.closure_times={'0:1:1':datetime.fromisoformat(NOW)+timedelta(minutes=1)}
    net=Network(g,{},c,CRS)
    assert net.route(origin,dest,NOW)['edge_ids'][0]=='0:1:0'


def test_backup_cannot_use_opposite_direction_or_same_bridge_way():
    g=graph();g[0][1][0]['bridge']='yes';g[0][1][0]['osmid']=999
    g[0][2][0]['bridge']='yes';g[0][2][0]['osmid']=999
    g,c,net,flood,known,origin,dest=context(g)
    primary=net.route(origin,dest,NOW)
    assert primary['uncertain_structures']
    assert net.backup(origin,dest,primary,NOW) is None


def test_capacity_enforcement_and_unknown():
    c=config();route={'travel_minutes':1,'distance_km':1}
    a,b=site('a',100),site('b',100)
    result=assign([(a,route),(b,route)],70,'L1',c)
    assert result[0] is a and result[2]=='sufficient' and a['properties']['available_capacity']==30
    result=assign([(a,route),(b,route)],70,'L2',c)
    assert result[0] is b and b['properties']['available_capacity']==30
    result=assign([(a,route),(b,route)],50,'L3',c)
    assert result[0] is None and result[3]=='insufficient_known_capacity'
    unknown=site('u')
    result=assign([(unknown,route)],5000,'L4',c)
    assert result[2]=='unknown' and unknown['properties']['capacity'] is None
    assert unknown['properties']['reserved_people']==0


def test_unknown_demand_not_derived_or_reserved():
    c=config();a=site('known',100);route={'travel_minutes':1,'distance_km':1}
    result=assign([(a,route)],None,'L',c)
    assert result[0] is None and result[3]=='capacity_unknown'
    assert a['properties']['available_capacity']==100


def test_ranking_verification_reuse_and_determinism():
    c=config();a,b=site('a'),site('b');route={'travel_minutes':1,'distance_km':1}
    assert assign([(b,route),(a,route)],None,'L1',c)[0] is a
    assert assign([(a,route),(b,route)],None,'L2',c)[0] is b
    a=site('a');b=site('b');b['properties']['verification_status']='verified'
    assert rank(b,route,None,c)['score']<rank(a,route,None,c)['score']


def test_deadlines_route_specific_offsets_and_static_unknown():
    c=config();route={'edge_exit_minutes':{'a':5,'b':20}}
    assert deadline(route,NOW,c)['latest_departure'] is None
    c.closure_times={'a':datetime.fromisoformat(NOW)+timedelta(minutes=40),'b':datetime.fromisoformat(NOW)+timedelta(minutes=50)}
    result=deadline(route,NOW,c)
    assert result['deadline_status']=='scenario_estimate' and result['limiting_edge_id']=='b'
    assert result['latest_departure']==NOW and result['urgency']=='elapsed'
    route['edge_exit_minutes']['b']=10
    assert deadline(route,NOW,c)['limiting_edge_id']=='a'
    assert deadline(None,NOW,c)['deadline_status']=='unavailable'


def test_closure_schedule_removes_infeasible_paths():
    g,c,net,flood,known,origin,dest=context(graph(False))
    c.closure_times={'1:3:0':datetime.fromisoformat(NOW)+timedelta(minutes=1)}
    net=Network(g,{},c,CRS)
    assert net.route(origin,dest,NOW) is None


def test_priority_explainable():
    c=config();p=locality();normal=score(p,c)
    bad=score(p,c,False,'unknown','elapsed')
    assert bad['score']>normal['score'] and bad['level']=='critical'
    assert sum(bad['contributions'].values())==bad['score']
    assert bad['reasons']


def site_frame(g,capacity=None):
    return gpd.GeoDataFrame({'id':['site1'],'name':['School'],'type':['school'],'source':['synthetic'],
      'verification_status':['unverified_candidate'],'capacity':[capacity],'capacity_source':[None]},geometry=[point(g,3)],crs=CRS)


def test_site_suitability_flood_unknown_and_types():
    g,c,net,flood,known,origin,dest=context();frame=site_frame(g)
    assert prepare_sites(frame,net,flood,known,c)[0]['properties']['suitability']=='eligible_candidate'
    flooded=point(g,3).buffer(20)
    assert prepare_sites(frame,net,flooded,known,c)[0]['properties']['suitability']=='ineligible'
    assert prepare_sites(frame,net,flood,box(0,0,1,1),c)[0]['properties']['suitability']=='ineligible'
    frame['type']='unapproved'
    assert prepare_sites(frame,net,flood,known,c)[0]['properties']['suitability']=='ineligible'


def synthetic_output():
    g,c,net,flood,known,origin,dest=context()
    localities=collection([feature(point(g,0),locality(),CRS)])
    summary={'replay_at':NOW}
    output=plan_all(g,site_frame(g),flood,known,localities,{},summary,c,CRS)
    return output,g,c,flood,known,localities,summary


def test_full_plan_and_no_site_no_route():
    output,g,c,flood,known,localities,summary=synthetic_output()
    p=output['plans'][0]
    assert p['provenance']['replay_at']==NOW
    assert p['provenance']['operationally_validated'] is False
    assert p['primary_route'] and p['backup_route'] and p['capacity_status']=='unknown'
    assert p['demand_people'] is None and p['deadline']['latest_departure'] is None
    bad_sites=site_frame(g);bad_sites['type']='excluded'
    output=plan_all(g,bad_sites,flood,known,localities,{},summary,c,CRS)
    assert 'no_safe_site' in output['plans'][0]['outcomes']
    impacts={'0:1:0':{'status':'closure_candidate'},'0:2:0':{'status':'unknown'}}
    output=plan_all(g,site_frame(g),flood,known,localities,impacts,summary,c,CRS)
    assert 'no_safe_route' in output['plans'][0]['outcomes']


def test_api_locality_slashes_cache_missing(monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import evacuation as service
    output,g,c,flood,known,localities,summary=synthetic_output()
    layers={'summary':{**summary,'bundle_sha256':'test','source':'scenario_assumption','assumptions':[],'limitations':[]}}
    monkeypatch.setattr(service,'inputs',lambda run:(layers,{'summary':'test'}))
    monkeypatch.setattr(service,'compute',lambda *args:output)
    monkeypatch.setattr(service,'load_config',lambda:c)
    monkeypatch.setattr(service,'CACHE',tmp_path)
    client=TestClient(app);base='/api/v1/runs/analysis-test'
    first=client.get(base+'/evacuation');assert first.status_code==200,first.text
    def no_recompute(*args): raise AssertionError('Recomputed cached plan')
    monkeypatch.setattr(service,'compute',no_recompute)
    assert client.get(base+'/evacuation').json()==first.json()
    assert client.get(base+'/safe-sites').status_code==200
    assert client.get(base+'/localities/osm/node/0/plan').status_code==200
    assert client.get(base+'/localities/missing/plan').status_code==404


def test_config_rejects_unsafe_defaults():
    from pydantic import ValidationError
    data=config().model_dump();data['excluded_road_statuses']=[]
    with pytest.raises(ValidationError): PlanningConfig.model_validate(data)


def test_zero_and_insufficient_capacity_are_not_site_safety_failures():
    output,g,c,flood,known,localities,summary=synthetic_output()
    c.locality_demands_people={'osm/node/0':60}
    for capacity in [0,50]:
        result=plan_all(g,site_frame(g,capacity),flood,known,localities,{},summary,c,CRS)
        p=result['plans'][0]
        assert p['primary_route'] is None
        assert 'insufficient_known_capacity' in p['outcomes']
        assert p['capacity_status']=='insufficient'
        assert result['counts']['no_safe_site']==0


def test_source_ids_unknown_and_capacity_validation():
    output,g,c,flood,known,localities,summary=synthetic_output()
    c.closure_times={'nonexistent':datetime.fromisoformat(NOW)}
    with pytest.raises(ValueError,match='unknown road'):
        plan_all(g,site_frame(g),flood,known,localities,{},summary,c,CRS)
    c.closure_times={};c.locality_demands_people={'missing':100}
    with pytest.raises(ValueError,match='unknown locality'):
        plan_all(g,site_frame(g),flood,known,localities,{},summary,c,CRS)
    c.locality_demands_people={}
    with pytest.raises(ValueError,match='capacity'):
        plan_all(g,site_frame(g,-1),flood,known,localities,{},summary,c,CRS)


def test_config_change_invalidates_cached_plan(monkeypatch,tmp_path):
    from app.services import evacuation as service
    output,g,c,flood,known,localities,summary=synthetic_output()
    layers={'summary':{**summary,'bundle_sha256':'test','source':'scenario_assumption','assumptions':[],'limitations':[]}}
    monkeypatch.setattr(service,'inputs',lambda run:(layers,{'summary':'test'}))
    monkeypatch.setattr(service,'compute',lambda *args:output)
    monkeypatch.setattr(service,'load_config',lambda:c)
    monkeypatch.setattr(service,'CACHE',tmp_path)
    first=service.get_evacuation('test')
    c.ranking.prior_assignment+=1
    second=service.get_evacuation('test')
    assert first['planning_id']!=second['planning_id']


def test_api_missing_run_and_base_replay_preserved():
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    response=client.get('/api/v1/runs/missing/evacuation')
    assert response.status_code==404
    assert client.get('/api/v1/runs/demo-yamuna-2023/zones/07/plan').status_code==200
