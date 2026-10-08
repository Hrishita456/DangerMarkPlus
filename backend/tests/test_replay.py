import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.replay import Fixture
from app.services import replay

client = TestClient(app)
RUN = "/api/v1/runs/demo-yamuna-2023"


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "danger-mark-api", "mode": "demo"}


def test_summary():
    response = client.get(f"{RUN}/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "demo-yamuna-2023"
    assert data["is_demo"] is True
    assert data["affected_population"] == 1352
    assert data["severity_counts"] == {"critical": 1, "high": 1, "warning": 1, "safe": 0}
    assert datetime.fromisoformat(data["replay_at"]).hour == 1
    assert response.headers["cache-control"] == "no-store"


def test_zones():
    response = client.get(f"{RUN}/zones")
    assert response.status_code == 200
    assert [zone["id"] for zone in response.json()["zones"]] == ["07", "11", "03"]


@pytest.mark.parametrize("zone_id,destination,population", [("07", "S4", 643), ("11", "S2", 291), ("03", "S1", 418)])
def test_zone_plan(zone_id, destination, population):
    response = client.get(f"{RUN}/zones/{zone_id}/plan")
    assert response.status_code == 200
    data = response.json()
    assert data["zone"]["id"] == zone_id
    assert data["zone"]["population"] == population
    assert data["primary_route"]["destination"]["id"] == destination
    for kind in ("primary", "backup"):
        route = data[f"{kind}_route"]
        assert route["zone_id"] == zone_id
        assert route["kind"] == kind
        assert route["stops"][0] == data["zone"]["name"]
        assert route["geometry"][0] == data["zone"]["position"]
        assert route["geometry"][-1] == route["destination"]["position"]


@pytest.mark.parametrize("path,code", [
    (f"{RUN}/zones/99/plan", "ZONE_NOT_FOUND"),
    ("/api/v1/runs/unknown/summary", "RUN_NOT_FOUND"),
    (f"{RUN}/summary?frame=unknown", "FRAME_NOT_FOUND"),
])
def test_not_found(path, code):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == code


@pytest.mark.parametrize("frame", ["evacuate", "prepare", "monitor", "clear"])
def test_shared_snapshot_invariants(frame):
    summary = client.get(f"{RUN}/summary?frame={frame}").json()
    listing = client.get(f"{RUN}/zones?frame={frame}").json()
    zones = listing["zones"]
    sites = {site["id"]: site for site in summary["sites"]}
    roads = {road["id"]: road for road in summary["roads"]}
    assert summary["affected_population"] == sum(zone["affected_population"] for zone in zones)
    assert sum(summary["severity_counts"].values()) == len(zones)
    assert summary["unassigned_population"] == 0
    assert summary["assignable_capacity"] == sum(site["capacity"] for site in sites.values() if site["assignable_in_demo"])
    for site in sites.values():
        assert site["assigned_population"] == sum(zone["affected_population"] for zone in zones if zone["destination_id"] == site["id"])
        if site["capacity"] is not None:
            assert site["available_capacity"] + site["assigned_population"] == site["capacity"]
        if not site["assignable_in_demo"]:
            assert site["assigned_population"] == 0
    for zone in zones:
        assert zone["destination_id"] in sites
        plan = client.get(f"{RUN}/zones/{zone['id']}/plan?frame={frame}").json()
        assert plan["zone"] == zone
        for field in ("run_id", "revision", "frame_id", "replay_at"):
            assert summary[field] == listing[field] == plan[field]
        for kind in ("primary", "backup"):
            route = plan[f"{kind}_route"]
            assert route["access_until"] == roads[route["access_road_id"]]["closes_at"]
            assert route["destination"] == sites[route["destination_id"]]
            departure = datetime.fromisoformat(route["departure_deadline"])
            assert departure >= datetime.fromisoformat(summary["replay_at"])
            assert departure + timedelta(minutes=route["travel_minutes"]) < datetime.fromisoformat(route["access_until"])
            assert departure < datetime.fromisoformat(zone["flood_arrival_at"])
            if kind == "backup":
                assert route["destination"]["available_capacity"] >= zone["affected_population"]
        if zone["severity"] == "safe":
            assert zone["departure_deadline"] is None
    if frame in ("monitor", "clear"):
        assert summary["affected_population"] == 0


def test_zone07_countdown_and_road_closures():
    plan = client.get(f"{RUN}/zones/07/plan").json()
    summary = client.get(f"{RUN}/summary").json()
    replay_at = datetime.fromisoformat(plan["replay_at"])
    assert (datetime.fromisoformat(plan["primary_route"]["departure_deadline"]) - replay_at).total_seconds() / 60 == 34
    assert (datetime.fromisoformat(plan["backup_route"]["departure_deadline"]) - replay_at).total_seconds() / 60 == 54
    roads = {road["id"]: road for road in summary["roads"]}
    assert roads["ito"]["closes_at"] == "2023-07-13T01:55:00+05:30"
    assert roads["ito"]["status"] == "closing"
    assert roads["khadar"]["status"] == "closed"
    assert plan["primary_route"]["access_road_id"] != "ito"


@pytest.mark.parametrize("origin", ["http://localhost:8443", "http://127.0.0.1:8443"])
def test_local_cors(origin):
    response = client.get(f"{RUN}/summary", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin


def test_unknown_origin_not_allowed():
    response = client.get(f"{RUN}/summary", headers={"Origin": "https://unrelated.example"})
    assert "access-control-allow-origin" not in response.headers


def test_fixture_edit_updates_all_api_views(tmp_path, monkeypatch):
    fixture = json.loads(replay.FIXTURE_PATH.read_text())
    fixture["zones"][0]["population"] = 650
    fixture["revision"] = "test-edited"
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(fixture))
    monkeypatch.setattr(replay, "FIXTURE_PATH", path)
    summary = client.get(f"{RUN}/summary").json()
    zones = client.get(f"{RUN}/zones").json()["zones"]
    plan = client.get(f"{RUN}/zones/07/plan").json()
    assert summary["affected_population"] == 1359
    assert zones[0]["population"] == plan["zone"]["population"] == 650
    assert plan["primary_route"]["destination"]["available_capacity"] == 850
    assert plan["revision"] == summary["revision"] == "test-edited"


def test_fixture_rejects_unknown_assignment_and_wrong_zone_route():
    fixture = json.loads(replay.FIXTURE_PATH.read_text())
    fixture["routes"][0]["destination_id"] = "missing"
    with pytest.raises(ValidationError):
        Fixture.model_validate(fixture)
    fixture = json.loads(replay.FIXTURE_PATH.read_text())
    fixture["zones"][0]["primary_route_id"] = "11-A"
    with pytest.raises(ValidationError):
        Fixture.model_validate(fixture)


def test_fixture_rejects_timezone_naive_replay():
    fixture = json.loads(replay.FIXTURE_PATH.read_text())
    fixture["frames"][0]["replay_at"] = "2023-07-13T01:21:00"
    with pytest.raises(ValidationError):
        Fixture.model_validate(fixture)


def test_zone_can_have_no_backup(tmp_path, monkeypatch):
    fixture = json.loads(replay.FIXTURE_PATH.read_text())
    next(zone for zone in fixture["zones"] if zone["id"] == "11")["backup_route_id"] = None
    path = tmp_path / "no-backup.json"
    path.write_text(json.dumps(fixture))
    monkeypatch.setattr(replay, "FIXTURE_PATH", path)
    response = client.get(f"{RUN}/zones/11/plan")
    assert response.status_code == 200
    assert response.json()["backup_route"] is None
    assert response.json()["primary_route"]["id"] == "11-A"
