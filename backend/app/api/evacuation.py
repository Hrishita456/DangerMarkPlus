from fastapi import APIRouter, HTTPException
from app.schemas.evacuation import EvacuationResult, LocalityPlan
from app.schemas.consequences import GeoCollection
from app.services.evacuation import get_evacuation

router=APIRouter(prefix='/api/v1')


@router.get('/runs/{run_id}/evacuation',response_model=EvacuationResult)
def evacuation(run_id: str):
    return get_evacuation(run_id)


@router.get('/runs/{run_id}/safe-sites',response_model=GeoCollection)
def safe_sites(run_id: str):
    return get_evacuation(run_id)['safe_sites']


@router.get('/runs/{run_id}/localities/{locality_id:path}/plan',response_model=LocalityPlan)
def locality_plan(run_id: str,locality_id: str):
    result=get_evacuation(run_id)
    for plan in result['plans']:
        if plan['locality']['locality_id']==locality_id: return plan
    raise HTTPException(404,{'code':'LOCALITY_PLAN_NOT_FOUND','message':'No affected-locality plan in this run.'})
