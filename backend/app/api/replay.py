from fastapi import APIRouter, Response

from app.schemas.replay import Plan, Summary, ZonesResponse
from app.services import replay

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health():
    return {"status": "ok", "service": "danger-mark-api", "mode": "demo"}


@router.get("/runs/{run_id}/summary", response_model=Summary)
def summary(run_id: str, response: Response, frame: str = "evacuate"):
    response.headers["Cache-Control"] = "no-store"
    return replay.get_summary(*replay.get_run(run_id, frame))


@router.get("/runs/{run_id}/zones", response_model=ZonesResponse)
def zones(run_id: str, response: Response, frame: str = "evacuate"):
    response.headers["Cache-Control"] = "no-store"
    return replay.get_zones(*replay.get_run(run_id, frame))


@router.get("/runs/{run_id}/zones/{zone_id}/plan", response_model=Plan)
def plan(run_id: str, zone_id: str, response: Response, frame: str = "evacuate"):
    response.headers["Cache-Control"] = "no-store"
    fixture, snapshot = replay.get_run(run_id, frame)
    return replay.get_plan(fixture, snapshot, zone_id)
