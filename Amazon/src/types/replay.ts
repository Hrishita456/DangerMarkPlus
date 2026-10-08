export type FrameId = "evacuate" | "prepare" | "monitor" | "clear";
export type Severity = "critical" | "high" | "warning" | "safe";
export type RouteKind = "primary" | "backup";
export interface Position { latitude: number; longitude: number }
export interface Site {
  id: string;
  name: string;
  kind: "shelter" | "facility" | "candidate";
  verification: "demo_only" | "unreviewed";
  position: Position;
  capacity: number | null;
  assignable_in_demo: boolean;
  elevation_m: number | null;
  usable_area_m2: number | null;
  assigned_population: number;
  available_capacity: number | null;
}
export interface Road {
  id: string;
  name: string;
  closes_at: string | null;
  water_depth_m: number | null;
  geometry: Position[];
  status: "open" | "closing" | "closed";
}
export interface Zone {
  id: string;
  name: string;
  population: number;
  affected_population: number;
  position: Position;
  severity: Severity;
  flood_arrival_at: string;
  departure_deadline: string | null;
  destination_id: string;
  primary_route_id: string;
  backup_route_id: string | null;
}
export interface Route {
  id: string;
  zone_id: string;
  kind: RouteKind;
  destination_id: string;
  destination: Site;
  stops: string[];
  distance_km: number;
  travel_minutes: number;
  travel_mode: "demo_vehicle";
  departure_deadline: string;
  access_road_id: string;
  access_until: string | null;
  geometry: Position[];
  status: "demo_available" | "closed";
}
export interface RunContext {
  run_id: string;
  revision: string;
  frame_id: FrameId;
  replay_at: string;
  is_demo: true;
}
export interface Summary extends RunContext {
  disclaimer: string;
  region_name: string;
  river_name: string;
  timezone: string;
  gauge_station: string;
  gauge_level_m: number;
  gauge_updated_at: string;
  next_update_at: string;
  projected_peak_m: number;
  projected_peak_at: string;
  demo_danger_level_m: number;
  affected_population: number;
  severity_counts: Record<Severity, number>;
  frames: { id: FrameId; replay_at: string }[];
  projections: { at: string; level_m: number }[];
  sites: Site[];
  roads: Road[];
  assignable_capacity: number;
  unassigned_population: number;
  illustrative_flood_polygon: Position[];
}
export interface ZonesResponse extends RunContext { zones: Zone[] }
export interface Plan extends RunContext {
  zone: Zone;
  primary_route: Route;
  backup_route: Route | null;
  avoid_road_ids: string[];
}
export interface ReplayData { summary: Summary; zones: Zone[]; plan: Plan }
