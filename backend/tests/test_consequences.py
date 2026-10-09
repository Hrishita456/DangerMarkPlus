"""Small synthetic GIS fixtures: no pilot data or network required."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
pytest.importorskip('rasterio', reason='Install the geospatial extra for consequence tests')
import geopandas as gpd
import networkx as nx
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, LineString, Point

from app.geospatial.connectivity import reachable, classify_access, Connectivity
from app.geospatial.consequences import Region, analyze, repository_path, severity
from app.geospatial.exposure import Population
from app.geospatial.flood import connected_mask, load_extent, terrain_extent
from app.geospatial.roads import impact
from app.geospatial.spatial import feature, metric_crs, project
from app.schemas.consequences import Scenario, ConsequenceSummary


def scenario():
    path = Path(__file__).resolve().parents[1] / 'config/phase3-pilot.json'
    return Scenario.model_validate_json(path.read_text())


def raster(path, values, crs='EPSG:32643', nodata=-9999, transform=None):
    values = np.asarray(values, dtype='float32')
    with rasterio.open(path, 'w', driver='GTiff', height=values.shape[0], width=values.shape[1], count=1,
                       dtype='float32', crs=crs, nodata=nodata, transform=transform or from_origin(0,20,10,10)) as dst:
        dst.write(values,1)
    return path


def test_population_fraction_zero_and_unknown(tmp_path):
    path = raster(tmp_path/'people.tif', [[100,-9999],[0,200]])
    p = Population.load(path, 'EPSG:32643', 'synthetic', 1)
    assert p.exposure(box(0,10,5,20))['exposed_population'] == 50
    assert p.exposure(box(0,0,20,20))['exposed_population'] == 300
    assert p.exposure(box(0,0,20,20))['coverage_fraction'] == .75
    assert p.exposure(box(0,0,10,10))['exposed_population'] == 0
    assert p.exposure(box(10,10,20,20))['exposed_population'] is None
    assert p.exposure(box(30,30,40,40))['coverage_fraction'] == 0
    assert p.exposure(box(0,0,1,1).intersection(box(5,5,6,6)))['exposed_population'] == 0


def test_population_negative_rejected(tmp_path):
    with pytest.raises(ValueError, match='Negative'):
        Population.load(raster(tmp_path/'bad.tif',[[-2]]), 'EPSG:32643', 'test',1)


def test_population_native_geographic_fraction(tmp_path):
    path=raster(tmp_path/'native.tif', [[100]],crs='EPSG:4326',transform=from_origin(77.25,28.65,.01,.01))
    p=Population.load(path,'EPSG:32643','native',1)
    assert p.exposure(p.cells[0])['exposed_population']==100
    with pytest.raises(ValueError, match='metre'):
        metric_crs('EPSG:4326')
    with pytest.raises(ValueError, match='metre'):
        metric_crs('EPSG:2263')


def test_flood_connected_not_diagonal_or_across_barrier():
    eligible=np.array([[1,0,1],[1,0,1],[0,1,1]],dtype=bool)
    seeds=np.zeros_like(eligible);seeds[0,0]=True
    result=connected_mask(eligible,seeds)
    assert result.sum()==2
    assert not result[2,1]


def test_terrain_and_precomputed_reject_rgb(tmp_path):
    dem=raster(tmp_path/'dem.tif',[[200,210],[200,-9999]])
    hydro=gpd.GeoDataFrame({'waterway':['river']},geometry=[LineString([(1,1),(1,19)])],crs='EPSG:32643')
    result=terrain_extent(dem,hydro,box(0,0,20,20),metric_crs('EPSG:32643'),scenario().flood)
    assert result.geometry.area==200
    assert result.known_area.area==300
    with pytest.raises(ValueError,match='metric CRS'):
        terrain_extent(dem,hydro,box(0,0,20,20),metric_crs('EPSG:32644'),scenario().flood)
    rgb=tmp_path/'rgb.tif'
    with rasterio.open(rgb,'w',driver='GTiff',count=4,dtype='uint8',width=2,height=2,crs='EPSG:32643',transform=from_origin(0,20,10,10)) as dst:
        dst.write(np.ones((4,2,2),dtype='uint8'))
    with pytest.raises(ValueError,match='RGB'):
        load_extent(rgb,box(0,0,20,20),'EPSG:32643','historical_evidence','test')
    binary=raster(tmp_path/'mask.tif',[[1,0],[0,-9999]])
    extent=load_extent(binary,box(0,0,20,20),'EPSG:32643','scenario_assumption','test')
    assert extent.geometry.area==100 and extent.known_area.area==300
    with pytest.raises(ValueError,match='0/1'):
        load_extent(dem,box(0,0,20,20),'EPSG:32643','historical_evidence','test')


@pytest.mark.parametrize('attrs,status', [({},'closure_candidate'),({'bridge':'yes'},'uncertain_structure'),
    ({'bridge':'no'},'closure_candidate'),({'layer':'1'},'uncertain_structure'),({'tunnel':'yes'},'uncertain_structure')])
def test_road_intersection_and_structures(attrs,status):
    result=impact(LineString([(0,0),(10,0)]),attrs,box(5,-1,15,1),box(-20,-20,20,20),1,2)
    assert result['status']==status
    assert result['flood_intersection_length_m']==5


def test_unaffected_proximity_unknown_roads():
    line=LineString([(0,0),(10,0)]);known=box(-20,-20,20,20)
    assert impact(line,{},box(0,10,10,15),known,1,2)['status']=='unaffected'
    assert impact(line,{},box(0,1,10,3),known,1,2)['status']=='near_flood'
    assert impact(line,{},box(0,10,10,15),box(0,0,1,1),1,2)['status']=='unknown'


def test_directed_connectivity_isolation_and_parallel_edges():
    g=nx.MultiDiGraph();g.add_edges_from([(1,2),(2,3),(4,3),(3,5)])
    baseline=reachable(g,[3],set());after=reachable(g,[3],{(2,3,0)})
    assert classify_access(1,baseline,after,after,False)[0]=='isolated'
    assert classify_access(4,baseline,after,after,False)[0]=='accessible'
    assert classify_access(5,baseline,after,after,False)[0]=='unknown' # wrong direction
    assert classify_access(4,baseline,after,{3},False)[0]=='at_risk_of_isolation'
    assert classify_access(4,baseline,after,after,True)[0]=='degraded_access'
    g.add_edge(2,3)
    assert 1 in reachable(g,[3],{(2,3,0)})


@pytest.mark.parametrize('flooded,distance,access,people,expected',[
 (True,0,'isolated',100,'critical'),(True,0,'accessible',0,'high'),
 (False,500,'at_risk_of_isolation',0,'high'),(False,100,'accessible',0,'warning'),
 (False,500,'accessible',100,'warning'),(False,500,'accessible',0,'safe'),
 (None,None,'accessible',0,'unknown'),(False,500,'unknown',0,'unknown')])
def test_explainable_severity(flooded,distance,access,people,expected):
    level,reasons=severity(flooded,distance,access,people,200)
    assert level==expected and reasons


def test_geojson_lon_lat_and_paths():
    original=Point(77.25,28.65);metric=project(original,'EPSG:4326','EPSG:32643')
    coords=feature(metric,{},'EPSG:32643')['geometry']['coordinates']
    assert coords==pytest.approx((77.25,28.65))
    with pytest.raises(ValueError,match='repository'):
        repository_path(Path('/tmp/project'),'../secret')


def synthetic_region(tmp_path):
    x,y=720000,3170000
    boundary=box(x,y,x+1000,y+1000)
    path=raster(tmp_path/'dem.tif',[[200]*10 for _ in range(10)], transform=from_origin(x,y+1000,100,100))
    hydro=gpd.GeoDataFrame({'waterway':['river']},geometry=[LineString([(x+50,y),(x+50,y+1000)])],crs='EPSG:32643')
    localities=gpd.GeoDataFrame({'id':['real-point'],'name':['Test locality']},geometry=[Point(x+100,y+500)],crs='EPSG:32643')
    g=nx.MultiDiGraph(crs='EPSG:32643')
    for n,px in [(1,x+100),(2,x+500),(3,x+900)]:g.add_node(n,x=px,y=y+500)
    g.add_edges_from([(1,2),(2,3),(3,2),(2,1)])
    return Region({'region_id':'synthetic'},'synthetichash',metric_crs('EPSG:32643'),boundary,hydro,localities,g,
                  Population([boundary],[1000],'synthetic',100),path)


def test_end_to_end_synthetic(tmp_path):
    s=scenario();region=synthetic_region(tmp_path)
    outputs=analyze(region,s,tmp_path,'analysis-'+'0'*24)
    summary=ConsequenceSummary.model_validate(outputs['summary'])
    assert summary.population.exposed_population==1000
    assert summary.flooded_area_km2==1
    assert summary.gateway_count==0
    assert summary.accessibility_counts=={'unknown':1}
    assert summary.road_counts=={'closure_candidate':4}
    assert outputs['localities']['features'][0]['properties']['flooded'] is True


def test_api_cache_reads_and_errors(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import consequences as service
    from app.geospatial import consequences as engine
    s=scenario();region=synthetic_region(tmp_path)
    # Reuse a tiny bundle file; service still exercises content addressing and atomic persisted output.
    s.bundle='bundle.json';(tmp_path/'bundle.json').write_text('{}')
    monkeypatch.setattr(service,'config',lambda:s)
    monkeypatch.setattr(service,'REPOSITORY',tmp_path)
    monkeypatch.setattr(service,'CACHE',tmp_path/'runs')
    monkeypatch.setattr(service,'region_data',lambda *args:region)
    client=TestClient(app)
    first=client.post('/api/v1/runs/analyze',json={'scenario_id':s.scenario_id})
    assert first.status_code==200,first.text
    assert first.json()['cached'] is False
    run=first.json()['run_id']
    second=client.post('/api/v1/runs/analyze',json={'scenario_id':s.scenario_id})
    assert second.json()['run_id']==run and second.json()['cached'] is True
    for layer in ['summary','localities','road-impacts','flood']:
        response=client.get(f'/api/v1/runs/{run}/{layer}')
        assert response.status_code==200,response.text
    assert client.post('/api/v1/runs/analyze',json={'scenario_id':'missing'}).status_code==404
    assert client.post('/api/v1/runs/analyze',json={'path':'/etc/passwd'}).status_code==422
    assert client.get('/api/v1/runs/unknown/flood').status_code==404
    monkeypatch.setattr(service,'region_data',lambda *args:(_ for _ in ()).throw(ValueError('Missing input')))
    assert client.post('/api/v1/runs/analyze',json={}).status_code==409
    response=client.options('/api/v1/runs/analyze',headers={'Origin':'http://localhost:8443',
        'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
    assert response.status_code==200


def test_bundle_missing_input_rejected(tmp_path):
    record={'path':'missing.tif','sha256':'0'*64}
    bundle={'metric_crs':'EPSG:32643','inputs':{'population':{'files':[record],'native_source_subset':record}},
            **{key:record for key in ('configuration','source_catalogue','validation_report','toolchain_lock')}}
    path=tmp_path/'bundle.json';path.write_text(json.dumps(bundle))
    with pytest.raises(ValueError,match='Missing or changed bundle input'):
        Region.load(tmp_path,path,100)


def test_precomputed_polygon_and_scenario_validation(tmp_path):
    from pydantic import ValidationError
    polygon=tmp_path/'extent.geojson'
    gpd.GeoDataFrame(geometry=[box(0,0,10,10)],crs='EPSG:32643').to_file(polygon,driver='GeoJSON')
    extent=load_extent(polygon,box(0,0,20,20),'EPSG:32643','scenario_assumption','test complete polygon')
    assert extent.geometry.area==100 and extent.known_area.area==400
    data=scenario().model_dump(mode='json');data['flood']['source']='historical_evidence'
    with pytest.raises(ValidationError): Scenario.model_validate(data)
    data=scenario().model_dump(mode='json');data['replay_at']='2023-07-13T18:00:00'
    with pytest.raises(ValidationError): Scenario.model_validate(data)


def test_outside_coverage_alone_is_not_flood_degradation(tmp_path):
    region=synthetic_region(tmp_path);s=scenario()
    s.thresholds.locality_buffer_m=200
    raster(region.dem_path, [[200]+[210]*9 for _ in range(10)], transform=from_origin(720000,3171000,100,100))
    region.localities.geometry=[Point(720900,3170500)]
    region.graph.add_node(4,x=721100,y=3170500)
    region.graph.add_edges_from([(3,4),(4,3)])
    output=analyze(region,s,tmp_path,'analysis-'+'0'*24)
    props=output['localities']['features'][0]['properties']
    assert props['nearby_unknown_directed_edges']>0
    assert props['nearby_affected_directed_edges']==0
    assert props['accessibility']=='accessible'
    assert props['flood_severity']=='safe'
