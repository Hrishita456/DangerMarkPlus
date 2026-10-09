import { ApiError, get } from "./client.ts";
import type { AnalysisData, AnalysisSummary, GeoSet, Locality, LocalityPlan, Planning, RoadImpact, Site } from "../types/analysis.ts";
export const DEMO_RUN = "demo-yamuna-2023";
export const PILOT_RUN = "analysis-1616d67b7b28fb2442d9747f";
export const isAnalysisRun = (id: string) => id.startsWith("analysis-");
const path = (run: string, resource: string) => `/runs/${encodeURIComponent(run)}/${resource}`;
const canonical = (value: unknown): string => JSON.stringify(value, (_key, item) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
export function validateAnalysis(run: string, data: AnalysisData) {
  const {summary, planning, localities, roads, flood, sites} = data;
  if (!isAnalysisRun(run) || summary.is_demo !== false || summary.run_id !== run || planning.run_id !== run
    || planning.provenance.bundle_sha256 !== summary.bundle_sha256 || planning.provenance.replay_at !== summary.replay_at
    || [localities, roads, flood, sites].some(layer => layer.type !== "FeatureCollection" || !Array.isArray(layer.features))
    || canonical(planning.safe_sites) !== canonical(sites)
    || planning.plans.some(plan => plan.provenance.run_id !== run || plan.provenance.bundle_sha256 !== summary.bundle_sha256
      || !localities.features.some(f => f.properties.locality_id === plan.locality.locality_id && canonical(f.properties) === canonical(plan.locality)))) {
    throw new ApiError("INCONSISTENT_ANALYSIS", "The analysis responses do not describe one consistent run. Retry.");
  }
  return data;
}
export async function loadAnalysis(run: string, signal: AbortSignal): Promise<AnalysisData> {
  if (!isAnalysisRun(run)) throw new ApiError("INVALID_RUN", "Select an analysis run.");
  const [summary, localities, roads, flood, planning, sites] = await Promise.all([
    get<AnalysisSummary>(path(run, "summary"), signal), get<GeoSet<Locality>>(path(run, "localities"), signal),
    get<GeoSet<RoadImpact>>(path(run, "road-impacts"), signal), get<GeoSet>(path(run, "flood"), signal),
    get<Planning>(path(run, "evacuation"), signal, 60000), get<GeoSet<Site>>(path(run, "safe-sites"), signal, 60000),
  ]);
  return validateAnalysis(run, {summary, localities, roads, flood, planning, sites});
}
export async function loadPlan(run: string, locality: string, expected: LocalityPlan, signal: AbortSignal) {
  const plan = await get<LocalityPlan>(path(run, `localities/${encodeURIComponent(locality)}/plan`), signal, 60000);
  if (canonical(plan) !== canonical(expected)) throw new ApiError("INCONSISTENT_PLAN", "The plan changed while loading. Retry the analysis.");
  return plan;
}
export const capacityLabel = (value: number | null | undefined) => value == null ? "Unknown" : value.toLocaleString("en-IN");
export const deadlineLabel = (deadline: LocalityPlan["deadline"] | null | undefined) => deadline?.latest_departure
  ? new Date(deadline.latest_departure).toLocaleString("en-IN", {timeZone: "Asia/Kolkata"}) + " IST · estimated mobilization start"
  : "Deadline unavailable";
export const selectedPlanRoute = (plan: LocalityPlan | undefined, route: "primary" | "backup") => plan?.[route === "primary" ? "primary_route" : "backup_route"] ?? null;
export interface Context { run: string; locality: string; route: "primary" | "backup" }
export function selectLocality(context: Context, locality: string): Context { return {...context, locality, route: "primary"}; }
export function candidateName(site: Site | null | undefined): string {
  if (!site) return "No candidate destination available";
  if (site.name?.trim()) return site.name.trim();
  const categories: Record<string, string> = {
    school: "school", college: "college", university: "university", hospital: "hospital",
    community_centre: "community building", community_center: "community building",
    townhall: "community building", government: "government building",
  };
  return `Candidate ${categories[site.type] || "public facility"}`;
}
const statusLabel = (value: string | undefined) => {
  const label = value?.trim().replace(/_/g, " ") || "unknown";
  return label.charAt(0).toUpperCase() + label.slice(1);
};
export function advisoryText(plan: LocalityPlan, kind: "primary" | "backup") {
  const route = selectedPlanRoute(plan, kind);
  return ["SIMULATED PREVIEW — NOTHING SENT", `${plan.locality.name} · ${plan.priority.level.toUpperCase()} priority`,
    `Candidate destination: ${candidateName(plan.selected_destination?.properties)}.`,
    `Verification: ${statusLabel(plan.selected_destination?.properties.verification_status)}. Capacity: ${statusLabel(plan.capacity_status)}.`,
    route ? `${kind} route: approximately ${route.distance_km.toFixed(2)} km / ${route.travel_minutes.toFixed(1)} minutes.` : `No ${kind} route available.`,
    deadlineLabel(kind === "backup" ? plan.backup_deadline : plan.deadline),
    "Conditional scenario plan. Destination, access and transport arrangements require authority verification."];
}
