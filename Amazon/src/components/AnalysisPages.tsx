import { useEffect, useRef, useState, type ReactNode } from "react";
import AnalysisMap from "./AnalysisMap";
import { advisoryText, candidateName, capacityLabel, deadlineLabel } from "../api/analysis";
import type useAnalysis from "../hooks/useAnalysis";
import type { LocalityPlan } from "../types/analysis";
type Page = "command" | "evacuation" | "flood" | "shelters";
type State = ReturnType<typeof useAnalysis>;
const words = (s: string) => s.replace(/_/g, " ");
const name = (plan?: LocalityPlan) => candidateName(plan?.selected_destination?.properties);
function Action({children, onClick}: {children: ReactNode; onClick: () => void}) {return <button type="button" className="button button-secondary" onClick={onClick}>{children}</button>;}
function Priority({plan}: {plan: LocalityPlan}) {return <span className={`status status-${plan.priority.level === "critical" ? "critical" : "warning"}`}>{plan.priority.level.toUpperCase()} PRIORITY</span>;}
function Reasons({plan}: {plan: LocalityPlan}) {
  return <><p>{words(plan.locality.accessibility)} · {plan.locality.access_reason}</p><p>Consequence severity: {plan.locality.flood_severity}. {plan.locality.reasons.join(" ")}</p>
    <p>{plan.primary_route ? "Primary route available under scenario assumptions." : "No feasible primary route."} Capacity {plan.capacity_status}. {plan.backup_route ? "Independent network backup available." : "No independent backup route available."}</p>
    <details><summary>Plan reasons and assumptions</summary>{[...plan.reasons,...plan.assumptions].map((reason,i) => <p key={i}>{reason}</p>)}</details></>;
}
export default function AnalysisPages({state, page, navigate}: {state: State; page: Page; navigate: (page: Page) => void}) {
  const {data, plan, route, kind} = state;
  const [advisory, setAdvisory] = useState(false);
  const [siteFilter, setSiteFilter] = useState("selected");
  useEffect(() => setAdvisory(false), [page, state.locality]);
  if (state.error) return <section className="plan-summary" role="alert"><div><div className="section-title">ANALYSIS UNAVAILABLE</div><p>{state.error}</p><Action onClick={state.retry}>RETRY ANALYSIS</Action></div></section>;
  if (state.loading || !data) return <section className="plan-summary" role="status"><div><div className="section-title">LOADING ANALYSIS RUN</div><p>Loading consistent consequences, geometry and evacuation plans. First-time planning may take up to a minute.</p></div></section>;
  const summary = data.summary;
  const timing = kind === "backup" ? plan?.backup_deadline : plan?.deadline;
  const toolbar = <div className="command-toolbar"><div className="section-kicker">ANALYSIS RUN · {words(summary.stage)}</div>
    <label className="analysis-select">LOCALITY <select aria-label="Select analysis locality" value={state.locality} onChange={e => state.selectLocality(e.target.value)} disabled={!data.planning.plans.length}>
      {!data.planning.plans.length && <option value="">No affected localities</option>}
      {data.planning.plans.map(p => <option key={p.locality.locality_id} value={p.locality.locality_id}>{p.locality.name} · {p.priority.level} priority</option>)}
    </select></label></div>;
  const provenance = <div className="evidence-note scenario-assumption"><span>SCENARIO ASSUMPTION</span><div>{summary.scenario.flood.assumption}<br/>{summary.timestamp_meaning} Not operationally validated.</div></div>;
  const routeButtons = <div className="site-filters" aria-label="Select analysis route">{(["primary","backup"] as const).map(k => <button type="button" key={k} aria-pressed={kind === k} className={kind === k ? "active" : ""} onClick={() => state.selectRoute(k)}>{k.toUpperCase()}{k === "backup" && !plan?.backup_route ? " · UNAVAILABLE" : ""}</button>)}</div>;
  const trip = route ? `${route.distance_km.toFixed(2)} KM · ~${route.travel_minutes.toFixed(1)} MIN` : kind === "backup" ? "No independent backup route available" : "No safe route available";
  const localityList = <div className="zone-list">{data.planning.plans.map(p => <div className="zone-row" key={p.locality.locality_id}>
    <div className="urgency-bar warning"/><div className="zone-name"><strong>{p.locality.name}</strong><Priority plan={p}/></div>
    <div className="zone-stat"><span>BUFFER EXPOSURE · EST.</span><strong>{capacityLabel(p.locality.approximate_population_exposure.exposed_population)}</strong></div>
    <div className="zone-stat"><span>ACCESS</span><strong>{words(p.locality.accessibility)}</strong></div><Action onClick={() => {state.selectLocality(p.locality.locality_id); navigate("evacuation");}}>VIEW PLAN</Action>
  </div>)}</div>;
  return <>
    {toolbar}{provenance}
    {!plan && <section className="plan-summary"><div className="section-title">No affected localities with evacuation plans in this run.</div></section>}
    {page === "command" && <div className="command-page command-state-prepare">
      {plan && <section className="decision-card state-prepare"><div className="command-hero-band hero-state-prepare"><div className="command-hero-action"><div className="hero-critical-pill">{plan.locality.name}</div><div className="hero-evacuate">{plan.priority.level.toUpperCase()} PRIORITY</div><small>PROVISIONAL SCENARIO PLAN</small></div>
        <div className="hero-risk-card"><div className="hero-risk-count"><strong>{capacityLabel(plan.locality.approximate_population_exposure.exposed_population)}</strong><span>EST. BUFFER EXPOSURE</span></div><div className="hero-deadline"><span>DEPARTURE</span><strong className="analysis-unknown">{deadlineLabel(timing)}</strong></div></div></div>
        <div className="decision-main"><div className="actions hero-actions"><Action onClick={() => navigate("evacuation")}>FULL PLAN</Action><Action onClick={() => setAdvisory(true)}>PREVIEW ADVISORY</Action>{routeButtons}</div>
          <div className="decision-at-glance"><div className="glance-tile where-tile"><div className="decision-label">CANDIDATE DESTINATION</div><div className="destination">{name(plan)}</div><div className="capacity-line">Capacity {plan.capacity_status} · {words(plan.selected_destination?.properties.verification_status || "unknown")}</div></div>
            <div className="glance-tile when-tile"><div className="decision-label">TIMING</div><strong>{deadlineLabel(timing)}</strong><p>Requires time-indexed closure evidence.</p></div><div className="glance-tile route-tile"><div className="decision-label">{kind.toUpperCase()} ROUTE</div><strong>{trip}</strong></div></div>
          <Reasons plan={plan}/><div className="site-note">{plan.locality.buffer_radius_m} m representative buffer, not an administrative boundary. Overlapping estimates are not additive. Evacuation headcount: {capacityLabel(plan.demand_people)}.</div>
        </div><aside className="avoid-panel"><div className="avoid-heading"><strong>SCENARIO ROAD IMPACT</strong></div><div className="avoid-item"><strong>{summary.road_counts.closure_candidate || 0} closure candidates</strong><p>Directed road edges, not confirmed closures.</p></div><div className="avoid-item"><strong>{summary.road_counts.uncertain_structure || 0} uncertain structures</strong><p>Excluded from planning routes.</p></div><Action onClick={() => navigate("flood")}>VIEW CONSEQUENCES</Action></aside></section>}
      <div className="zone-heading"><div className="section-title">AFFECTED / ACCESS-UNCERTAIN LOCALITIES</div><span>{data.planning.plans.length} PLANS</span></div>{localityList}
    </div>}
    {page === "evacuation" && <div className="evacuation-page">
      {plan && <section className="plan-summary"><div><div className="summary-status"><Priority plan={plan}/><strong>{plan.locality.name}</strong></div><div className="summary-route">{name(plan)}</div><div className="summary-meta">{trip} · Capacity {plan.capacity_status}</div><p>{deadlineLabel(timing)}</p></div><Action onClick={() => setAdvisory(true)}>PREVIEW ADVISORY</Action></section>}
      <div className="evacuation-layout"><section className="evacuation-map-panel"><div className="section-head"><div className="section-title">EVACUATION MAP · ANALYSIS</div>{routeButtons}</div><AnalysisMap data={data} plan={plan} kind={kind} onSelect={state.selectLocality}/></section>
        {plan && <section className="route-brief"><div className="route-brief-head"><Priority plan={plan}/><span>{plan.locality.name}</span></div><div className="brief-section"><span>CANDIDATE DESTINATION</span><strong>{name(plan)}</strong><p>{words(plan.selected_destination?.properties.verification_status || "unknown")}</p><p>Capacity: {plan.capacity_status} · Headcount: {capacityLabel(plan.demand_people)}</p><Action onClick={() => navigate("shelters")}>INSPECT CANDIDATE</Action></div>
          <div className="brief-section"><span>{kind.toUpperCase()} ROUTE</span><strong>{trip}</strong><p>{route?.road_names.join(" → ") || "No named road sequence available."}</p><p>{deadlineLabel(timing)}</p>{!route && <p>{kind === "backup" ? plan.backup_reason : plan.outcomes.join(" · ")}</p>}</div>
          {route && <details><summary>Route constraints · {route.bottlenecks.length} bottlenecks</summary>{route.bottlenecks.map(b => <p key={b.edge_id}>{b.reason} · {b.edge_id}</p>)}{route.assumptions.map(a => <p key={a}>{a}</p>)}</details>}<Reasons plan={plan}/></section>}
      </div></div>}
    {page === "flood" && <div className="intelligence-page"><div className="page-intro"><div><div className="section-kicker">CALCULATED CONSEQUENCES</div><div className="page-title">FLOOD INTELLIGENCE</div><p>One assumed stage. No measured progression or arrival forecast.</p></div></div>
      <section className="flood-summary"><div className="gauge-reading"><span>WET AREA · INCLUDES CHANNEL</span><strong>{summary.flooded_area_km2.toFixed(2)} km²</strong></div><div className="gauge-reading"><span>ESTIMATED EXPOSED PEOPLE</span><strong>{capacityLabel(summary.population.exposed_population)}</strong><small>~1 KM POPULATION INFORMATION</small></div><div className="arrival-reading"><span>DEGRADED ACCESS</span><strong>{summary.accessibility_counts.degraded_access || 0}</strong><small>{summary.accessibility_counts.isolated || 0} ISOLATED · {summary.accessibility_counts.unknown || 0} UNKNOWN</small></div></section>
      <div className="operational-grid"><section className="affected-zones"><div className="section-title">SELECTED LOCALITY</div>{plan ? <><h3>{plan.locality.name}</h3><Priority plan={plan}/><Reasons plan={plan}/></> : <p>No affected locality selected.</p>}<p>Population coverage of wet area: {(summary.population.coverage_fraction * 100).toFixed(1)}%.</p></section><section className="road-impact"><div className="section-title">DIRECTED ROAD EDGES</div>{Object.entries(summary.road_counts).map(([status,count]) => <div key={status}><strong>{words(status)}</strong><b>{count.toLocaleString("en-IN")}</b></div>)}</section></div>
      <section className="evacuation-map-panel"><div className="section-head"><div className="section-title">SCENARIO FOOTPRINT & SELECTED ROUTES</div></div><AnalysisMap data={data} plan={plan} kind={kind} onSelect={state.selectLocality}/></section>
      <details className="site-note"><summary>Evidence, coverage and limitations</summary>{[...summary.assumptions,...summary.limitations,...summary.population.assumptions].map((a,i) => <p key={i}>{a}</p>)}</details>{localityList}</div>}
    {page === "shelters" && <div className="safe-sites-page"><div className="page-intro"><div><div className="section-kicker">CANDIDATE SITES & CAPACITY</div><div className="page-title">SAFE-SITE CANDIDATES</div><p>Model eligibility does not establish shelter approval or availability.</p></div><div className="site-filters">{["selected","eligible","all"].map(f => <button type="button" key={f} className={siteFilter === f ? "active" : ""} onClick={() => setSiteFilter(f)}>{f.toUpperCase()}</button>)}</div></div>
      <section className="capacity-deficit"><div><span>{data.sites.features.length} CANDIDATES</span><strong>{data.planning.counts.eligible_candidate_sites} pass scenario checks · selected locality capacity {plan?.capacity_status || "unknown"}</strong></div></section>
      <div className="safe-site-list">{data.sites.features.filter(f => siteFilter === "all" || (siteFilter === "eligible" ? f.properties.suitability === "eligible_candidate" : f.properties.id === plan?.selected_destination?.properties.id)).map(({properties: site}) => <section className="safe-site-card candidate-site" key={site.id}><div className="site-card-head"><span className="site-symbol candidate-symbol">△</span><div><strong>{site.name || `Unnamed ${words(site.type)}`}</strong><small>{site.id} · {words(site.verification_status)}</small></div><span className="status status-warning">CANDIDATE</span></div><div className="site-metrics three"><div><span>CAPACITY</span><strong>{capacityLabel(site.capacity)}</strong></div><div><span>AVAILABLE CAPACITY</span><strong>{capacityLabel(site.available_capacity)}</strong></div><div><span>FLOOD CLEARANCE</span><strong>{site.flood_clearance_m == null ? "Unknown" : `${Math.round(site.flood_clearance_m)} m`}</strong></div></div><div className="site-note">{words(site.suitability)} · {site.reasons.join(" ")}<p>Capacity source: {site.capacity_source || "Unknown"}. {site.assigned_locality_ids.length} provisional locality assignments; not passenger counts.</p></div></section>)}</div>
      {siteFilter === "selected" && !plan?.selected_destination && <div className="site-note">No candidate destination assigned. Choose All to inspect available records.</div>}
    </div>}
    {advisory && plan && <AnalysisAdvisory plan={plan} kind={kind} onClose={() => setAdvisory(false)}/>}
  </>;
}
function AnalysisAdvisory({plan, kind, onClose}: {plan: LocalityPlan; kind: "primary" | "backup"; onClose: () => void}) {
  const [simulated, setSimulated] = useState(false);
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {const previous = document.activeElement as HTMLElement; dialog.current?.focus(); return () => previous?.focus();}, []);
  return <div className="advisory-overlay"><section ref={dialog} tabIndex={-1} className="advisory-preview" role="dialog" aria-modal="true" aria-label="Analysis advisory preview" onKeyDown={e => {
    if (e.key === "Escape") onClose();
    if (e.key === "Tab") {const buttons = Array.from(dialog.current?.querySelectorAll("button") || []); const i = buttons.indexOf(document.activeElement as HTMLButtonElement); if ((e.shiftKey && i <= 0) || (!e.shiftKey && i === buttons.length-1)) {e.preventDefault(); buttons[e.shiftKey ? buttons.length-1 : 0]?.focus();}}
  }}><div className="section-kicker">ANALYSIS PLAN · PREVIEW ONLY</div><div className="advisory-title">{simulated ? "SIMULATION COMPLETE · NOTHING SENT" : "ADVISORY PREVIEW"}</div>{advisoryText(plan,kind).map((line,i) => <p key={i}>{line}</p>)}<div className="advisory-actions">{!simulated && <Action onClick={() => setSimulated(true)}>SIMULATE ISSUANCE</Action>}<Action onClick={onClose}>CLOSE PREVIEW</Action></div></section></div>;
}
