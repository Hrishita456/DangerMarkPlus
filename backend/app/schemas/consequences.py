from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Thresholds(StrictModel):
    locality_buffer_m: float = Field(gt=0, le=5000)
    warning_distance_m: float = Field(ge=0, le=5000)
    road_near_m: float = Field(ge=0, le=1000)
    closure_intersection_m: float = Field(gt=0, le=1000)
    snap_max_m: float = Field(gt=0, le=5000)
    gateway_ring_m: float = Field(gt=0, le=5000)
    gateway_flood_clearance_m: float = Field(ge=0, le=5000)
    population_rounding_people: int = Field(gt=0)


class FloodSpec(StrictModel):
    method: Literal["connected_terrain", "precomputed"]
    source: Literal["historical_evidence", "terrain_approximation", "scenario_assumption"]
    assumption: str = Field(min_length=1)
    water_surface_m: float | None = None
    vertical_reference: str | None = None
    seed_waterway_types: list[str] = Field(default_factory=lambda: ["river"])
    seed_buffer_m: float = Field(default=30, gt=0, le=1000)
    path: str | None = None

    @model_validator(mode="after")
    def coherent(self):
        if self.method == "connected_terrain":
            if self.water_surface_m is None or not self.vertical_reference or self.source != "terrain_approximation":
                raise ValueError("Terrain requires a labelled surface/datum and terrain_approximation provenance")
        elif not self.path or self.source == "terrain_approximation":
            raise ValueError("Precomputed extent requires a path and evidence/assumption source")
        return self


class Scenario(StrictModel):
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,100}$")
    bundle: str
    stage: str
    replay_at: AwareDatetime
    timestamp_meaning: str
    evidence_limitations: list[str] = Field(default_factory=list)
    flood: FloodSpec
    thresholds: Thresholds


class AnalyzeRequest(StrictModel):
    scenario_id: str = Field(default="yamuna-2023-illustrative-terrain", max_length=101)


class AnalyzeResponse(StrictModel):
    run_id: str
    scenario_id: str
    summary_url: str
    cached: bool


class PopulationEstimate(StrictModel):
    exposed_population: int | None
    coverage_fraction: float = Field(ge=0, le=1)
    population_source: str
    estimate_kind: str
    rounding_people: int
    assumptions: list[str]


class ConsequenceSummary(StrictModel):
    run_id: str
    region_id: str
    scenario_id: str
    stage: str
    replay_at: AwareDatetime
    timestamp_meaning: str
    is_demo: bool = False
    operationally_validated: bool = False
    source: str
    algorithm_version: str
    bundle_sha256: str
    scenario: Scenario
    flooded_area_km2: float
    flood_known_coverage_fraction: float
    population: PopulationEstimate
    locality_counts: dict[str, int]
    locality_exposure_counts: dict[str, int]
    accessibility_counts: dict[str, int]
    road_counts: dict[str, int]
    road_count_unit: str
    gateway_count: int
    assumptions: list[str]
    limitations: list[str]


class GeoFeature(StrictModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict
    properties: dict


class GeoCollection(StrictModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoFeature]
