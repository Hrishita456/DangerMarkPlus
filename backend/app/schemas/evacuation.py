from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from app.schemas.consequences import StrictModel, GeoCollection, GeoFeature


class Ranking(StrictModel):
    minutes: float = Field(ge=0)
    kilometres: float = Field(ge=0)
    unverified: float = Field(ge=0)
    unknown_capacity: float = Field(ge=0)
    prior_assignment: float = Field(ge=0)


class PriorityConfig(StrictModel):
    severity: dict[str, float]
    access: dict[str, float]
    exposure_per_1000: float = Field(ge=0)
    exposure_cap: float = Field(ge=0)
    no_route: float = Field(ge=0)
    capacity_unknown: float = Field(ge=0)
    deadline_elapsed: float = Field(ge=0)
    deadline_soon: float = Field(ge=0)
    urgency_minutes: float = Field(gt=0)
    critical_threshold: float
    high_threshold: float
    moderate_threshold: float

    @model_validator(mode='after')
    def valid_weights(self):
        if not self.critical_threshold > self.high_threshold > self.moderate_threshold >= 0:
            raise ValueError('Priority thresholds must increase')
        if set(self.severity) != {'critical','high','warning','safe','unknown'} or set(self.access) != {'isolated','at_risk_of_isolation','degraded_access','accessible','unknown'}:
            raise ValueError('All severity/access categories require weights')
        if any(v < 0 for v in [*self.severity.values(), *self.access.values()]):
            raise ValueError('Priority weights must be nonnegative')
        return self


class PlanningConfig(StrictModel):
    mode: Literal['road_vehicle']
    site_clearance_m: float = Field(ge=0)
    road_attachment_tolerance_m: float = Field(ge=0)
    snap_max_m: float = Field(gt=0)
    connector_speed_kph: float = Field(gt=0, le=30)
    speed_factor: float = Field(gt=0, le=1)
    default_speed_kph: float = Field(gt=0, le=150)
    class_speeds_kph: dict[str, float]
    excluded_road_statuses: list[str]
    eligible_types: list[str]
    ranking: Ranking
    mobilization_minutes: float = Field(ge=0)
    safety_minutes: float = Field(ge=0)
    closure_times: dict[str, AwareDatetime]
    closure_time_source: Literal['scenario_assumption', 'observed']
    locality_demands_people: dict[str, int]
    priority: PriorityConfig

    @model_validator(mode='after')
    def safe_config(self):
        if any(v <= 0 or v > 150 for v in self.class_speeds_kph.values()):
            raise ValueError('Invalid assumed speed')
        if any(v <= 0 for v in self.locality_demands_people.values()):
            raise ValueError('Demand overrides must be positive confirmed planning inputs')
        if not {'closure_candidate','uncertain_structure','unknown'} <= set(self.excluded_road_statuses):
            raise ValueError('Unsafe and unknown edges must be excluded')
        return self


class Deadline(StrictModel):
    deadline_status: Literal['unavailable','scenario_estimate','observed_constraint_estimate']
    latest_departure: AwareDatetime | None
    latest_vehicle_departure: AwareDatetime | None
    urgency: Literal['unknown','elapsed','soon','later']
    limiting_edge_id: str | None
    reasons: list[str]


class Route(StrictModel):
    geometry: GeoFeature
    distance_km: float
    travel_minutes: float
    edge_ids: list[str]
    edge_exit_minutes: dict[str, float]
    road_names: list[str]
    bottlenecks: list[dict]
    uncertain_structures: list[dict]
    connectors: list[dict]
    assumptions: list[str]


class LocalityPlan(StrictModel):
    locality: dict
    provenance: dict
    demand_people: int | None
    demand_source: str
    priority: dict
    selected_destination: GeoFeature | None
    capacity_status: Literal['sufficient','insufficient','unknown']
    primary_route: Route | None
    backup_route: Route | None
    backup_status: Literal['available','unavailable']
    backup_reason: str
    deadline: Deadline
    backup_deadline: Deadline | None
    outcomes: list[str]
    feasible_destinations: list[dict]
    reasons: list[str]
    assumptions: list[str]


class EvacuationResult(StrictModel):
    run_id: str
    planning_id: str
    algorithm_version: str
    configuration: PlanningConfig
    provenance: dict
    operationally_validated: bool = False
    counts: dict[str, int]
    plans: list[LocalityPlan]
    safe_sites: GeoCollection
    assumptions: list[str]
