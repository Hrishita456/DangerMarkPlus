from pathlib import Path

from fastapi import HTTPException

from app.schemas.replay import (
    Fixture, Frame, FrameChoice, Plan, RoadStatus, Route, SiteCapacity,
    Summary, Zone, ZonesResponse,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "demo-yamuna-2023.json"


def load_fixture() -> Fixture:
    # Tiny local file: intentionally re-read so fixture edits require no JSX edits
    # or process restart. Each endpoint validates its complete input snapshot.
    return Fixture.model_validate_json(FIXTURE_PATH.read_text())


def get_run(run_id: str, frame_id: str) -> tuple[Fixture, Frame]:
    fixture = load_fixture()
    if run_id != fixture.run_id:
        raise HTTPException(404, {"code": "RUN_NOT_FOUND", "message": "Demo run not found."})
    frame = next((item for item in fixture.frames if item.id == frame_id), None)
    if frame is None:
        raise HTTPException(404, {"code": "FRAME_NOT_FOUND", "message": "Replay snapshot not found."})
    return fixture, frame


def context(fixture: Fixture, frame: Frame) -> dict:
    return dict(run_id=fixture.run_id, revision=fixture.revision, frame_id=frame.id,
                replay_at=frame.replay_at, is_demo=True)


def get_zones(fixture: Fixture, frame: Frame) -> ZonesResponse:
    routes = {item.id: item for item in fixture.routes}
    zones = []
    for spec in fixture.zones:
        severity = frame.zone_severities[spec.id]
        primary = routes[spec.primary_route_id]
        zones.append(Zone(**spec.model_dump(), severity=severity,
                          affected_population=spec.population if severity != "safe" else 0,
                          departure_deadline=primary.departure_deadline if severity != "safe" else None,
                          destination_id=primary.destination_id))
    zones.sort(key=lambda zone: (zone.departure_deadline is None, zone.departure_deadline or frame.replay_at, zone.id))
    return ZonesResponse(**context(fixture, frame), zones=zones)


def get_summary(fixture: Fixture, frame: Frame) -> Summary:
    zones = get_zones(fixture, frame).zones
    sites = []
    for site in fixture.sites:
        assigned = sum(zone.affected_population for zone in zones if zone.destination_id == site.id)
        if site.capacity is not None and assigned > site.capacity:
            raise ValueError(f"Demo fixture over-assigns {site.id}")
        sites.append(SiteCapacity(**site.model_dump(), assigned_population=assigned,
                                 available_capacity=None if site.capacity is None else site.capacity - assigned))
    roads = [RoadStatus(**road.model_dump(), status=(
        "closed" if road.closes_at and road.closes_at <= frame.replay_at
        else "closing" if road.closes_at else "open"
    )) for road in fixture.roads]
    affected = sum(zone.affected_population for zone in zones)
    return Summary(
        **context(fixture, frame), disclaimer=fixture.disclaimer,
        region_name=fixture.region_name, river_name=fixture.river_name, timezone=fixture.timezone,
        gauge_station=fixture.gauge_station, gauge_level_m=frame.gauge_level_m,
        gauge_updated_at=frame.gauge_updated_at, next_update_at=frame.next_update_at,
        projected_peak_m=frame.projected_peak_m, projected_peak_at=frame.projected_peak_at,
        demo_danger_level_m=fixture.demo_danger_level_m, affected_population=affected,
        severity_counts={severity: sum(zone.severity == severity for zone in zones)
                         for severity in ("critical", "high", "warning", "safe")},
        frames=[FrameChoice(id=item.id, replay_at=item.replay_at) for item in fixture.frames],
        sites=sites, roads=roads, projections=frame.projections,
        assignable_capacity=sum(site.capacity or 0 for site in sites if site.assignable_in_demo),
        unassigned_population=affected - sum(site.assigned_population for site in sites),
        illustrative_flood_polygon=fixture.illustrative_flood_polygon,
    )


def get_plan(fixture: Fixture, frame: Frame, zone_id: str) -> Plan:
    zone = next((zone for zone in get_zones(fixture, frame).zones if zone.id == zone_id), None)
    if zone is None:
        raise HTTPException(404, {"code": "ZONE_NOT_FOUND", "message": f"Zone {zone_id} is not in this demo run."})
    summary = get_summary(fixture, frame)
    sites = {site.id: site for site in summary.sites}
    roads = {road.id: road for road in summary.roads}
    routes = {route.id: route for route in fixture.routes}

    def route_view(route_id: str) -> Route:
        spec = routes.get(route_id)
        if spec is None:
            raise HTTPException(409, {"code": "PLAN_UNAVAILABLE", "message": "A complete plan is unavailable."})
        access = roads[spec.access_road_id]
        return Route(**spec.model_dump(), destination=sites[spec.destination_id],
                     access_until=access.closes_at,
                     status="closed" if access.status == "closed" else "demo_available")

    return Plan(**context(fixture, frame), zone=zone,
                primary_route=route_view(zone.primary_route_id),
                backup_route=route_view(zone.backup_route_id) if zone.backup_route_id else None,
                avoid_road_ids=[road.id for road in roads.values()
                                if road.id in ("ito", "khadar") and road.status != "open"])
