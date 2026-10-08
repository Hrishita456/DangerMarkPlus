from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Severity = Literal["critical", "high", "warning", "safe"]
FrameId = Literal["evacuate", "prepare", "monitor", "clear"]
RouteKind = Literal["primary", "backup"]
NonNegative = Annotated[int, Field(ge=0)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(Model):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class Site(Model):
    id: str
    name: str
    kind: Literal["shelter", "facility", "candidate"]
    verification: Literal["demo_only", "unreviewed"]
    position: Position
    capacity: NonNegative | None
    assignable_in_demo: bool
    elevation_m: float | None = None
    usable_area_m2: float | None = None


class SiteCapacity(Site):
    assigned_population: NonNegative
    available_capacity: NonNegative | None


class Road(Model):
    id: str
    name: str
    closes_at: AwareDatetime | None
    water_depth_m: Annotated[float, Field(ge=0)] | None = None
    geometry: list[Position] = Field(min_length=2)


class RoadStatus(Road):
    status: Literal["open", "closing", "closed"]


class RouteSpec(Model):
    id: str
    zone_id: str
    kind: RouteKind
    destination_id: str
    stops: list[str] = Field(min_length=2)
    distance_km: Annotated[float, Field(gt=0)]
    travel_minutes: Annotated[int, Field(gt=0)]
    travel_mode: Literal["demo_vehicle"]
    departure_deadline: AwareDatetime
    access_road_id: str
    geometry: list[Position] = Field(min_length=2)


class ZoneSpec(Model):
    id: str
    name: str
    population: NonNegative
    position: Position
    flood_arrival_at: AwareDatetime
    primary_route_id: str
    backup_route_id: str | None


class Projection(Model):
    at: AwareDatetime
    level_m: float


class Frame(Model):
    id: FrameId
    replay_at: AwareDatetime
    gauge_level_m: float
    gauge_updated_at: AwareDatetime
    next_update_at: AwareDatetime
    projected_peak_m: float
    projected_peak_at: AwareDatetime
    zone_severities: dict[str, Severity]
    projections: list[Projection]


class Fixture(Model):
    run_id: str
    revision: str
    is_demo: Literal[True]
    disclaimer: str
    region_name: str
    river_name: str
    timezone: str
    gauge_station: str
    demo_danger_level_m: float
    default_frame: FrameId
    frames: list[Frame]
    zones: list[ZoneSpec]
    sites: list[Site]
    roads: list[Road]
    routes: list[RouteSpec]
    illustrative_flood_polygon: list[Position] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_references(self):
        def by_id(items):
            result = {item.id: item for item in items}
            if len(result) != len(items):
                raise ValueError("Duplicate fixture IDs")
            return result

        zones, sites, roads, routes, frames = map(
            by_id, (self.zones, self.sites, self.roads, self.routes, self.frames)
        )
        if self.default_frame not in frames:
            raise ValueError("Default frame does not exist")
        for route in routes.values():
            if route.zone_id not in zones or route.destination_id not in sites or route.access_road_id not in roads:
                raise ValueError("Route refers to an unknown zone, site, or road")
            if not sites[route.destination_id].assignable_in_demo:
                raise ValueError("Unreviewed sites cannot receive demo assignments")
            if route.geometry[0] != zones[route.zone_id].position or route.geometry[-1] != sites[route.destination_id].position:
                raise ValueError("Route geometry must connect its zone and destination")
        for zone in zones.values():
            for kind, route_id in (("primary", zone.primary_route_id), ("backup", zone.backup_route_id)):
                if route_id is None and kind == "backup":
                    continue
                route = routes.get(route_id)
                if route is None or route.zone_id != zone.id or route.kind != kind:
                    raise ValueError("Zone route ownership/kind mismatch")
        for frame in frames.values():
            if set(frame.zone_severities) != set(zones):
                raise ValueError("Every frame must classify every zone")
            if not frame.gauge_updated_at <= frame.replay_at < frame.next_update_at:
                raise ValueError("Invalid frame update timestamps")
        return self


class FrameChoice(Model):
    id: FrameId
    replay_at: AwareDatetime


class RunContext(Model):
    run_id: str
    revision: str
    frame_id: FrameId
    replay_at: AwareDatetime
    is_demo: Literal[True]


class Zone(ZoneSpec):
    severity: Severity
    affected_population: NonNegative
    departure_deadline: AwareDatetime | None
    destination_id: str


class ZonesResponse(RunContext):
    zones: list[Zone]


class Summary(RunContext):
    disclaimer: str
    region_name: str
    river_name: str
    timezone: str
    gauge_station: str
    gauge_level_m: float
    gauge_updated_at: AwareDatetime
    next_update_at: AwareDatetime
    projected_peak_m: float
    projected_peak_at: AwareDatetime
    demo_danger_level_m: float
    affected_population: NonNegative
    severity_counts: dict[Severity, NonNegative]
    frames: list[FrameChoice]
    sites: list[SiteCapacity]
    roads: list[RoadStatus]
    projections: list[Projection]
    assignable_capacity: NonNegative
    unassigned_population: NonNegative
    illustrative_flood_polygon: list[Position]


class Route(RouteSpec):
    destination: SiteCapacity
    access_until: AwareDatetime | None
    status: Literal["demo_available", "closed"]


class Plan(RunContext):
    zone: Zone
    primary_route: Route
    backup_route: Route | None
    avoid_road_ids: list[str]
