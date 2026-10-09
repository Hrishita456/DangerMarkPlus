from fastapi import APIRouter
from app.schemas.consequences import AnalyzeRequest, AnalyzeResponse, GeoCollection
from app.services.consequences import create_run, read_run

router = APIRouter(prefix='/api/v1')


@router.post('/runs/analyze', response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    return create_run(request.scenario_id)


@router.get('/runs/{run_id}/localities', response_model=GeoCollection)
def localities(run_id: str):
    return read_run(run_id, 'localities')


@router.get('/runs/{run_id}/road-impacts', response_model=GeoCollection)
def roads(run_id: str):
    return read_run(run_id, 'road-impacts')


@router.get('/runs/{run_id}/flood', response_model=GeoCollection)
def flood(run_id: str):
    return read_run(run_id, 'flood')
