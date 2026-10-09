import test from "node:test";
import assert from "node:assert/strict";
import { advisoryText, capacityLabel, deadlineLabel, DEMO_RUN, loadAnalysis, loadPlan, selectLocality, selectedPlanRoute, validateAnalysis } from "./analysis.ts";
import type { AnalysisData, LocalityPlan } from "../types/analysis.ts";
const run = "analysis-test";
const geo = (features: unknown[] = []) => ({type:"FeatureCollection", features});
function fixture() {
  const locality = {locality_id:"osm/node/1", name:"Test locality", flood_severity:"warning", accessibility:"degraded_access", approximate_population_exposure:{exposed_population:100}, reasons:[], access_reason:"Road effects"};
  const route = {distance_km:1,travel_minutes:5,geometry:{type:"Feature",geometry:{type:"LineString",coordinates:[[77.2,28.6],[77.21,28.61]]},properties:{}}, edge_ids:["1:2:0"]};
  const site = {type:"Feature",geometry:{type:"Point",coordinates:[77.21,28.61]},properties:{id:"site1",name:"Candidate School",verification_status:"unverified_candidate",capacity:null,available_capacity:null}};
  const plan = {locality,provenance:{run_id:run,bundle_sha256:"bundle",replay_at:"2023-07-13T18:00:00+05:30"},priority:{level:"moderate"}, selected_destination:site,capacity_status:"unknown",demand_people:null,primary_route:route,backup_route:null,deadline:{latest_departure:null,deadline_status:"unavailable"},backup_deadline:null};
  const sites=geo([site]);
  return {summary:{run_id:run,is_demo:false,bundle_sha256:"bundle",replay_at:plan.provenance.replay_at},localities:geo([{type:"Feature",geometry:{type:"Point",coordinates:[77.2,28.6]},properties:locality}]),roads:geo(),flood:geo(),sites,planning:{run_id:run,provenance:plan.provenance,plans:[plan],safe_sites:sites}} as unknown as AnalysisData;
}
function mockApi(data: AnalysisData) {
  const resources: Record<string,unknown> = {summary:data.summary,localities:data.localities,"road-impacts":data.roads,flood:data.flood,evacuation:data.planning,"safe-sites":data.sites,plan:data.planning.plans[0]};
  return async (url: string | URL | Request) => new Response(JSON.stringify(resources[String(url).split("/").at(-1)!]),{status:200,headers:{"Content-Type":"application/json"}});
}
test("analysis run loads a consistent aggregate from all six APIs", async t => {
  const data=fixture();let calls=0;t.mock.method(globalThis,"fetch",async (url: string) => {calls++;return mockApi(data)(url);});
  const result=await loadAnalysis(run,new AbortController().signal);assert.equal(calls,6);assert.equal(result.summary.run_id,run);
});
test("individual locality endpoint matches the selected aggregate plan", async t => {
  const data=fixture();t.mock.method(globalThis,"fetch",mockApi(data));
  const plan=await loadPlan(run,"osm/node/1",data.planning.plans[0],new AbortController().signal);assert.equal(plan.locality.locality_id,"osm/node/1");
});
test("demo and analysis responses cannot mix", async () => {
  assert.throws(() => validateAnalysis(DEMO_RUN,fixture()));
  const data=fixture();data.summary.run_id=DEMO_RUN;assert.throws(() => validateAnalysis(run,data));
  await assert.rejects(loadAnalysis(DEMO_RUN,new AbortController().signal));
});
test("changed destination or capacity between endpoints is rejected", async t => {
  const data=fixture();const expected=structuredClone(data.planning.plans[0]);data.planning.plans[0].capacity_status="sufficient";
  t.mock.method(globalThis,"fetch",mockApi(data));await assert.rejects(loadPlan(run,"osm/node/1",expected,new AbortController().signal),/changed/);
});
test("site ledger inconsistency is rejected", () => {
  const data=fixture();data.sites=structuredClone(data.sites);data.sites.features[0].properties.capacity=100;
  assert.throws(() => validateAnalysis(run,data),/consistent/);
});
test("locality changes retain the run and reset route; page navigation is independent", () => {
  const context={run,locality:"osm/node/1",route:"backup" as const};
  const selected=selectLocality(context,"osm/node/2");assert.deepEqual(selected,{run,locality:"osm/node/2",route:"primary"});
  // The shared context contains no page field; views consume the same context.
  const views=["command","evacuation","flood","shelters"].map(() => selected);
  assert.ok(views.every(value => value===selected));assert.equal(context.route,"backup");
});
test("backup unavailable never falls back to primary geometry", () => {
  const plan=fixture().planning.plans[0];assert.equal(selectedPlanRoute(plan,"backup"),null);
  assert.equal(selectedPlanRoute(plan,"primary"),plan.primary_route);
  plan.backup_route={...plan.primary_route!,distance_km:2};assert.equal(selectedPlanRoute(plan,"backup")?.distance_km,2);
});
test("unknown capacity and static deadline stay unknown in cards and preview", () => {
  const plan=fixture().planning.plans[0];assert.equal(capacityLabel(null),"Unknown");assert.equal(capacityLabel(0),"0");
  assert.equal(deadlineLabel(plan.deadline),"Deadline unavailable");
  const preview=advisoryText(plan,"backup").join(" ");assert.match(preview,/No backup route/);assert.match(preview,/NOTHING SENT/);assert.match(preview,/Deadline unavailable/);assert.doesNotMatch(preview,/01:55|verified shelter|delivered/i);
});
test("API failures propagate without demo fallbacks", async t => {
  t.mock.method(globalThis,"fetch",async () => {throw new Error("offline");});await assert.rejects(loadAnalysis(run,new AbortController().signal),/unavailable/);
});
test("empty affected-locality and geometry collections remain valid", () => {
  const data=fixture();data.planning.plans=[];data.localities.features=[];assert.equal(validateAnalysis(run,data).planning.plans.length,0);
});

test("advisory prefers real names and displays statuses as readable labels", () => {
  const preview = advisoryText(fixture().planning.plans[0], "primary").join(" ");
  assert.match(preview, /Candidate destination: Candidate School\./);
  assert.match(preview, /Verification: Unverified candidate\. Capacity: Unknown\./);
  assert.doesNotMatch(preview, /unverified_candidate/);
});
test("unnamed advisory destinations use categories, never raw source IDs", () => {
  const plan = fixture().planning.plans[0];
  const site = plan.selected_destination!.properties;
  site.name = null;
  site.id = "osm/way/292167792";
  for (const [type, expected] of [["school", "Candidate school"], ["community_centre", "Candidate community building"], ["unknown", "Candidate public facility"]]) {
    site.type = type;
    const preview = advisoryText(plan, "primary").join(" ");
    assert.ok(preview.includes(`Candidate destination: ${expected}.`));
    assert.doesNotMatch(preview, /osm\/way\/292167792/);
  }
  site.name = "  ";
  assert.match(advisoryText(plan, "primary").join(" "), /Candidate public facility/);
  plan.selected_destination = null;
  assert.match(advisoryText(plan, "primary").join(" "), /No candidate destination available/);
});
