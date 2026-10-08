import { useEffect, useRef, useState, type ReactNode } from "react";
import EvacuationMap from "./components/EvacuationMap";
import useReplay from "./hooks/useReplay";
import { date, distance, level, minutesUntil, number, remaining, time } from "./api/format";
import type { FrameId, Plan, Route, RouteKind, Severity, Site, Summary, Zone } from "./types/replay";

type Page = "command" | "evacuation" | "flood" | "shelters";
type CommandState = FrameId;
const navItems: Array<{ id: Page; label: string }> = [
  { id: "command", label: "Command Center" },
  { id: "evacuation", label: "Evacuation" },
  { id: "flood", label: "Flood Intelligence" },
  { id: "shelters", label: "Safe Sites" },
];

function ArrowIcon({ direction = "right" }: { direction?: "right" | "down" }) {
  return (
    <svg
      className={`icon ${direction === "down" ? "rotate" : ""}`}
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="M5 12h14M14 7l5 5-5 5" />
    </svg>
  );
}

function SignalIcon() {
  return (
    <svg className="brand-mark" viewBox="0 0 42 42" aria-hidden="true">
      <path d="M21 3 39 35H3L21 3Z" />
      <path d="M21 14v10M21 29v1" />
    </svg>
  );
}

function VerifiedIcon() {
  return (
    <svg className="verified-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.8 20 6v5.4c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6l8-3.2Z" />
      <path d="m8.2 12 2.4 2.4 5.2-5.2" />
    </svg>
  );
}

function Button({
  children,
  variant = "primary",
  onClick,
}: {
  children: ReactNode;
  variant?: "primary" | "secondary" | "quiet" | "navy";
  onClick?: () => void;
}) {
  return (
    <button className={`button button-${variant}`} type="button" onClick={onClick}>
      {children}
    </button>
  );
}

function Status({ children, tone }: { children: ReactNode; tone: "critical" | "warning" | "safe" | "cyan" }) {
  const icons = { critical: "!", warning: "△", safe: "✓", cyan: "i" };
  return <span className={`status status-${tone}`}><i aria-hidden="true">{icons[tone]}</i>{children}</span>;
}

const severityTone = (severity: Severity) => severity === "high" ? "warning" : severity;
const actionState = (summary: Summary, zone: Zone): CommandState => zone.severity === "critical" ? "evacuate"
  : zone.severity === "high" || zone.severity === "warning" ? "prepare"
  : summary.frame_id === "clear" ? "clear" : "monitor";
const stateLabel: Record<CommandState, string> = { evacuate: "EVACUATION ACTIVE", prepare: "HIGH RISK", monitor: "WATCH", clear: "ALL CLEAR" };
const deadlineFor = (zone: Zone, route: Route) => zone.severity === "safe" ? null : route.departure_deadline;

function AppShell({ page, setPage, summary, unavailable, children }: {
  page: Page; setPage: (page: Page) => void; summary?: Summary; unavailable: boolean; children: ReactNode;
}) {
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><SignalIcon /><div><div className="brand-name">DANGER MARK<span>+</span></div><div className="brand-subtitle">Evacuation intelligence</div></div></div>
      <nav className="nav" aria-label="Primary"><div className="nav-label">Response console</div>
        {navItems.map(item => <button className={`nav-item ${page === item.id ? "active" : ""}`} key={item.id} onClick={() => setPage(item.id)} type="button">
          <span>{item.label}</span>{item.id === "command" && <span className="nav-alert" />}
        </button>)}
      </nav>
      <div className="sidebar-footer"><div className="system-meta">{summary?.region_name || "DANGER MARK+"} • DEMO REPLAY</div><div className="system-meta">NOT HISTORICAL EVIDENCE</div></div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div><div className="eyebrow">{summary ? `${summary.river_name} FLOOD RESPONSE` : "REPLAY CONNECTION"} <span className={`active-word state-${summary?.frame_id || "monitor"}`}>• {summary ? stateLabel[summary.frame_id] : unavailable ? "DATA UNAVAILABLE" : "WAITING FOR API"}</span></div>
          <div className="topbar-title">{navItems.find(item => item.id === page)?.label}</div></div>
        <div className="header-metrics">
          <div><span>GAUGE</span><strong>{summary ? level(summary.gauge_level_m) : "—"}</strong></div>
          <div><span>PEAK</span><strong>{summary ? level(summary.projected_peak_m) : "—"}</strong></div>
          <div><span>AFFECTED</span><strong>{summary ? number(summary.affected_population) : "—"}</strong></div>
          <div><span>CRITICAL ZONES</span><strong className={summary?.severity_counts.critical ? "critical-text" : ""}>{summary?.severity_counts.critical ?? "—"}</strong></div>
        </div>
        <div className="clock"><span>DEMO REPLAY TIME</span><strong>{summary ? time(summary.replay_at, summary.timezone) : "—"}</strong><small>{summary ? date(summary.replay_at, summary.timezone) : unavailable ? "UNAVAILABLE" : "LOADING"}</small></div>
      </header>
      {children}
    </main>
  </div>;
}

function EmergencyStrip({ summary, zone, route, onView }: { summary: Summary; zone: Zone; route: Route; onView: () => void }) {
  const state = actionState(summary, zone);
  const deadline = deadlineFor(zone, route);
  return <div className={`emergency-strip strip-${state}`}>
    <span className="strip-status">{zone.severity.toUpperCase()} • DEMO</span>
    <strong>{zone.name}</strong><span className="strip-divider" />
    {deadline ? <><span><strong>{number(zone.affected_population)}</strong> PEOPLE</span><span className="strip-divider" />
      <span>LEAVE BY <strong>{time(deadline, summary.timezone)}</strong></span><span className="strip-divider" /><span>TO <strong>{route.destination_id}</strong></span></>
      : <strong>NO EVACUATION REQUIRED IN THIS SNAPSHOT</strong>}
    <button type="button" onClick={onView}>VIEW PLAN <ArrowIcon /></button>
  </div>;
}

function CommandCenter({ summary, zones, plan, route, setPage, selectZone, setFrame, selectRoute, openAdvisory }: {
  summary: Summary; zones: Zone[]; plan: Plan; route: Route;
  setPage: (page: Page) => void; selectZone: (id: string) => void; setFrame: (frame: FrameId) => void;
  selectRoute: (kind: RouteKind) => void; openAdvisory: () => void;
}) {
  const zone = plan.zone;
  const state = actionState(summary, zone);
  const isEvacuation = state === "evacuate", isPrepare = state === "prepare";
  const showBackup = route.kind === "backup";
  const active = zone.severity !== "safe";
  const deadline = deadlineFor(zone, route);
  const clock = (value: string | null) => time(value, summary.timezone);
  const others = zones.filter(item => item.id !== zone.id);
  const margin = summary.demo_danger_level_m - summary.gauge_level_m;
  const hero = {
    evacuate: { label: `CRITICAL EVACUATION - ${zone.name}`, headline: "EVACUATE NOW" },
    prepare: { label: `${zone.severity.toUpperCase()} RISK - ${zone.name}`, headline: "PREPARE TO EVACUATE" },
    monitor: { label: `WATCH - ${zone.name}`, headline: "MONITOR" },
    clear: { label: `ALL CLEAR - ${zone.name}`, headline: "NO EVACUATION REQUIRED" },
  }[state];
  const roadWatch = summary.roads.filter(road => plan.avoid_road_ids.includes(road.id));

  return <div className={`command-page command-state-${state}`}>
    <div className="command-toolbar">
      <div className="section-kicker"><span className="pulse-ring" />{active ? "PRIORITY ACTION • DEMO" : "SYSTEM STATUS • DEMO"}</div>
      <div className="state-preview"><span>DEMO SNAPSHOT</span><div>
        {summary.frames.map(frame => <button className={summary.frame_id === frame.id ? "active" : ""} type="button" onClick={() => setFrame(frame.id)} key={frame.id}>{frame.id.toUpperCase()}</button>)}
      </div></div>
    </div>
    <section className={`decision-card state-${state} ${showBackup && active ? "backup-active" : ""}`}>
      <div className={`command-hero-band hero-state-${state}`}>
        <div className="command-hero-action"><div className="hero-critical-pill"><span className="hero-alert-icon">{isEvacuation ? "!" : state === "clear" ? "✓" : "i"}</span>{hero.label}</div><div className="hero-evacuate">{hero.headline}</div></div>
        <div className="hero-risk-card">
          <div className="hero-risk-count"><strong>{active ? number(zone.affected_population) : state === "monitor" ? level(Math.abs(margin)) : "0"}</strong><span>{active ? "PEOPLE AT RISK" : state === "monitor" ? `${margin >= 0 ? "BELOW" : "ABOVE"} DEMO DANGER MARK` : "ZONES AT RISK"}</span></div>
          <div className="hero-deadline"><span>{active ? "LEAVE BY" : state === "monitor" ? "NEXT UPDATE" : "GAUGE MARGIN"}</span><strong>{active ? clock(deadline) : state === "monitor" ? `${minutesUntil(summary.next_update_at, summary.replay_at)} MIN` : level(Math.abs(margin))}</strong><small>{active ? remaining(deadline, summary.replay_at) : "DEMO SNAPSHOT"}</small></div>
        </div>
      </div>
      <div className="decision-main">
        <div className="actions hero-actions">
          {active && <Button variant="navy" onClick={openAdvisory}>{isPrepare ? "PREVIEW PRE-EVACUATION NOTICE" : "PREVIEW EVACUATION ADVISORY"}<ArrowIcon /></Button>}
          {!active && <Button variant="navy" onClick={() => setPage("flood")}>VIEW SCENARIO <ArrowIcon /></Button>}
          {active && <Button variant="secondary" onClick={() => setPage("evacuation")}>FULL PLAN</Button>}
          {active && plan.backup_route && <Button variant="quiet" onClick={() => selectRoute(showBackup ? "primary" : "backup")}>{showBackup ? "RETURN TO PRIMARY ROUTE" : "BACKUP ROUTE"}</Button>}
        </div>
        {active ? <div className="decision-at-glance">
          <div className="glance-tile where-tile"><div className="decision-label">WHERE</div><div className="destination">{route.destination.name}</div>
            <div className="trip-time"><strong>{route.travel_minutes} MIN</strong><span className="trip-divider">•</span><b>{distance(route.distance_km)}</b></div>
            <div className="capacity-line">{route.destination.available_capacity === null ? "CAPACITY UNKNOWN" : `${number(route.destination.available_capacity)} SPACES UNRESERVED`}</div></div>
          <div className="glance-tile when-tile"><div className="decision-label">WHEN</div><div className="leave-time"><span>LEAVE BY <strong>{clock(deadline)}</strong></span><small>{remaining(deadline, summary.replay_at)}</small></div></div>
          <div className="glance-tile route-tile"><div className="decision-label">ROUTE</div><div className="route-tile-title">{route.kind.toUpperCase()} {route.id}</div><div className="route-clear"><span>✓</span>{route.status === "closed" ? "DEMO CLOSED" : "DEMO AVAILABLE"}</div></div>
        </div> : <div className={`readiness-tiles ${state === "monitor" ? "four" : ""}`}>
          <div><span>DEMO SHELTERS</span><strong>{summary.sites.filter(site => site.assignable_in_demo).length}</strong><small>{number(summary.assignable_capacity)} CAPACITY</small></div>
          <div><span>ROADS LISTED</span><strong>{summary.roads.length}</strong><small>{summary.roads.filter(road => road.status === "closed").length} DEMO CLOSURES</small></div>
          <div><span>LAST GAUGE UPDATE</span><strong>{clock(summary.gauge_updated_at)}</strong><small>DEMO STATION READING</small></div>
          {state === "monitor" && <div><span>NEXT CHECK</span><strong>{clock(summary.next_update_at)}</strong><small>IN {minutesUntil(summary.next_update_at, summary.replay_at)} MIN</small></div>}
        </div>}
        {active && <div className="destination-confidence">DEMO DESTINATION • NOT AUTHORITY VERIFIED • {route.travel_mode.replace(/_/g, " ").toUpperCase()}</div>}
        {active ? <div className="safe-window">
          <div className="safe-window-head"><span>DEMO EXIT WINDOW</span><strong>{remaining(deadline, summary.replay_at)}</strong></div>
          <div className="window-track"><span className="window-safe" /><span className="window-warning" /><span className="window-critical" /><i style={{ left: "0%" }} /></div>
          <div className="window-labels"><span>NOW {clock(summary.replay_at)}</span><span>ILLUSTRATIVE WINDOW</span><span>{clock(deadline)} • LEAVE BY</span></div>
        </div> : <div className="gauge-window">
          <div className="safe-window-head"><span>GAUGE VS DEMO DANGER MARK</span><strong>{level(Math.abs(margin))} {margin >= 0 ? "BELOW" : "ABOVE"}</strong></div>
          <div className="gauge-track"><span /><i className="peak-marker" /><i className="danger-marker" /></div>
          <div className="window-labels"><span>CURRENT {level(summary.gauge_level_m)}</span><span>PEAK {level(summary.projected_peak_m)}</span><span>DANGER {level(summary.demo_danger_level_m)}</span></div>
        </div>}
        {showBackup && active && <div className="backup-explanation"><strong>BACKUP DEMO PLAN</strong><span>Alternative destination: {route.destination.name}. Primary assignments are unchanged.</span><div><b>{distance(route.distance_km)}</b><b>{route.travel_minutes} MIN TRAVEL</b></div></div>}
        {active && <>
          <div className={`route-section-label ${showBackup ? "backup" : ""}`}>{route.kind.toUpperCase()} ROUTE</div>
          <div className="route-line" aria-label={`${route.kind} evacuation route`}>
            {route.stops.map((stop, index) => <div className="route-segment" key={`${index}-${stop}`}><span className={index === 0 ? "route-origin" : index === route.stops.length - 1 ? "route-end" : ""}>{stop}</span>{index < route.stops.length - 1 && <ArrowIcon />}</div>)}
          </div>
          <div className="timing-row"><div><span>DEMO ACCESS UNTIL</span><strong>{clock(route.access_until)}</strong></div><div><span>DEMO FLOOD ARRIVAL</span><strong>{clock(zone.flood_arrival_at)}</strong></div><p>Leave before <strong>{clock(deadline)}</strong> to reach {route.destination_id} within this demo access window.</p></div>
        </>}
      </div>
      <aside className={active ? "avoid-panel" : `road-watch state-${state}`}>
        <div className="avoid-heading"><span className="blocked-icon">{active ? "×" : "i"}</span><div><small>DEMO ROUTE SAFETY</small><strong>{active ? "DO NOT USE" : "ROAD WATCH"}</strong></div></div>
        {roadWatch.map(road => <div className="avoid-item" key={road.id}><div className="avoid-road">{road.name}</div>
          <div className={`avoid-status ${road.status === "closed" ? "critical-text" : "warning-text"}`}>{road.status === "closed" ? "DEMO CLOSED" : `CLOSES IN ${minutesUntil(road.closes_at!, summary.replay_at)} MIN`}</div>
          <p>Demo closure: {clock(road.closes_at)}.{road.water_depth_m !== null && road.status === "closed" ? ` Mock depth ${level(road.water_depth_m)}.` : ""}</p>
        </div>)}
        <div className="avoid-foot">{roadWatch.length} demo road restrictions • no field observations</div>
      </aside>
    </section>
    <div className="zone-heading"><div><div className="section-title">{active ? "OTHER PRIORITY ZONES" : "OTHER ZONE STATUS"}</div><p>Ordered by primary-route departure deadline</p></div><span>{others.filter(item => item.severity !== "safe").length} OF {others.length} REQUIRE ACTION</span></div>
    <div className="zone-list">{others.map(item => <ZoneRow key={item.id} zone={item} summary={summary} onView={() => { selectZone(item.id); setPage("evacuation"); }} />)}</div>
  </div>;
}

function ZoneRow({ zone, summary, onView }: { zone: Zone; summary: Summary; onView: () => void }) {
  return <div className="zone-row"><div className={`urgency-bar ${zone.severity === "critical" || zone.severity === "high" ? "high" : "warning"}`} />
    <div className="zone-name"><strong>{zone.name}</strong><Status tone={severityTone(zone.severity)}>{zone.severity.toUpperCase()}</Status></div>
    <div className="zone-stat"><span>POPULATION</span><strong>{number(zone.population)}</strong></div>
    <div className="zone-stat"><span>LEAVE BY</span><strong>{time(zone.departure_deadline, summary.timezone)}</strong><small>{remaining(zone.departure_deadline, summary.replay_at)}</small></div>
    <div className="zone-stat"><span>{zone.severity === "safe" ? "STANDBY SITE" : "PRIMARY ASSIGNMENT"}</span><strong>DEMO SHELTER {zone.destination_id}</strong></div>
    <Button variant="quiet" onClick={onView}>VIEW PLAN <ArrowIcon /></Button>
  </div>;
}

function Evacuation({ summary, zones, plan, route, selectZone, selectRoute, openAdvisory }: {
  summary: Summary; zones: Zone[]; plan: Plan; route: Route; selectZone: (id: string) => void; selectRoute: (kind: RouteKind) => void; openAdvisory: () => void;
}) {
  const zone = plan.zone, deadline = deadlineFor(zone, route);
  const label = zone.severity === "safe" ? "STANDBY" : zone.severity === "critical" ? "EVACUATE NOW" : "PREPARE";
  const alternative = route.kind === "primary" ? plan.backup_route : plan.primary_route;
  return <div className="evacuation-page">
    <div className="command-toolbar"><div className="section-kicker">DEMO EVACUATION PLAN</div><div className="site-filters" aria-label="Select zone">{zones.map(item => <button type="button" key={item.id} className={zone.id === item.id ? "active" : ""} onClick={() => selectZone(item.id)}>{item.name}</button>)}</div></div>
    <section className="plan-summary"><div>
      <div className="summary-status"><Status tone={severityTone(zone.severity)}>{label}</Status><span>{zone.name} • {number(zone.population)} PEOPLE</span></div>
      <div className="summary-route"><span>LEAVE BY <strong>{time(deadline, summary.timezone)}</strong></span><ArrowIcon /><span>{route.destination.name}</span></div>
      <div className="summary-meta">{distance(route.distance_km)} <span /> {route.travel_minutes} MIN <span /> DEMO ACCESS UNTIL {time(route.access_until, summary.timezone)}</div>
    </div>{deadline && <Button onClick={openAdvisory}>PREVIEW ADVISORY <ArrowIcon /></Button>}</section>
    <div className="evacuation-layout">
      <section className="evacuation-map-panel"><div className="section-head"><div><div className="section-title">EVACUATION MAP</div><p>OpenStreetMap • illustrative demo geometry</p></div><Status tone="cyan">{route.kind.toUpperCase()} • DEMO</Status></div><EvacuationMap summary={summary} plan={plan} selectedRoute={route.kind} /></section>
      <section className="route-brief">
        <div className="route-brief-head"><Status tone={severityTone(zone.severity)}>{label}</Status><span>{zone.name}</span></div>
        <div className="route-brief-population"><strong>{number(zone.population)}</strong> PEOPLE</div>
        <div className="route-brief-deadline"><span>LEAVE BY</span><strong>{time(deadline, summary.timezone)}</strong></div>
        <div className="brief-section"><span>DESTINATION • DEMO ONLY</span><strong>{route.destination.name}</strong></div>
        <div className="brief-section"><span>{route.kind.toUpperCase()} ROUTE {route.id}</span><div className="brief-route">
          {route.stops.slice(1).map((stop, index, stops) => <div key={`${index}-${stop}`}><i /><strong>{stop}</strong>{index < stops.length - 1 && <span />}</div>)}
        </div><div className="brief-trip"><strong>{route.travel_minutes} MIN</strong><span />{distance(route.distance_km)}</div></div>
        <div className="brief-avoid"><span>DEMO DO NOT USE</span>{summary.roads.filter(road => plan.avoid_road_ids.includes(road.id)).map(road => <strong key={road.id}>{road.name} • {road.status === "closed" ? "CLOSED" : time(road.closes_at, summary.timezone)}</strong>)}</div>
        {alternative && <div className="brief-backup"><div><span>{alternative.kind.toUpperCase()}</span><strong>{alternative.destination.name}</strong></div><div><strong>{alternative.travel_minutes} MIN</strong><span>{distance(alternative.distance_km)}</span></div></div>}
        {alternative && <div className="actions"><Button variant="secondary" onClick={() => selectRoute(alternative.kind)}>USE {alternative.kind.toUpperCase()} ROUTE</Button></div>}
        <div className="assignment-order"><span>ASSIGNMENT STATUS</span><strong>DEMO SHELTER</strong><i>→</i><strong>NO AUTHORITY VERIFICATION</strong></div>
        <div className="site-note">{remaining(deadline, summary.replay_at)} • no live dispatch</div>
      </section>
    </div>
  </div>;
}

function FloodIntelligence({ summary, zones, plan, route }: { summary: Summary; zones: Zone[]; plan: Plan; route: Route }) {
  const [projectionIndex, setProjectionIndex] = useState(0);
  const clock = (value: string | null) => time(value, summary.timezone);
  const deadline = deadlineFor(plan.zone, route);
  return <div className="intelligence-page">
    <div className="page-intro"><div><div className="section-kicker">DEMO FLOOD INTELLIGENCE</div><div className="page-title">{plan.zone.name} • SCENARIO CONTEXT</div><p>Synthetic projections for the selected snapshot. Not historical observations.</p></div>
      <div className="replay-control" aria-label="Highlight forecast point">{summary.projections.map((point, index) => <button className={index === projectionIndex ? "active" : ""} onClick={() => setProjectionIndex(index)} key={point.at} type="button">{index === 0 ? "NOW" : index === summary.projections.length - 1 ? "PEAK" : clock(point.at)}</button>)}</div>
    </div>
    <section className="flood-summary"><div className="gauge-reading"><span>YAMUNA DEMO GAUGE</span><strong>{level(summary.gauge_level_m)}</strong><small>SNAPSHOT {clock(summary.replay_at)}</small></div>
      <div className="gauge-reading"><span>DEMO PROJECTED PEAK</span><strong>{level(summary.projected_peak_m)}</strong><small>EXPECTED {clock(summary.projected_peak_at)}</small></div>
      <div className="arrival-reading"><span>DEMO FLOOD ARRIVAL</span><strong>{clock(plan.zone.flood_arrival_at)}</strong><small>{plan.zone.name}</small></div></section>
    <section className="simple-timeline"><div className="section-head"><div><div className="section-title">DEMO FLOOD PROGRESSION</div><p>Highlight only • replay remains {clock(summary.replay_at)}</p></div><Status tone="cyan">DEMO</Status></div>
      <div className="timeline-track">{summary.projections.map((point, index) => <button className={`timeline-stop ${index === 0 ? "flood" : index === 1 ? "warning" : "critical"} ${projectionIndex === index ? "selected" : ""}`} type="button" onClick={() => setProjectionIndex(index)} key={point.at}><i /><span>{clock(point.at)}</span><strong>{level(point.level_m)}</strong><small>{index === summary.projections.length - 1 ? "DEMO PEAK" : "SYNTHETIC PROJECTION"}</small></button>)}</div>
    </section>
    <div className="operational-grid"><section className="affected-zones"><div className="section-title">ZONE STATUS</div>{zones.map(zone => <div key={zone.id}><strong>{zone.name}</strong><Status tone={severityTone(zone.severity)}>{zone.severity.toUpperCase()}</Status><span>{number(zone.affected_population)} AFFECTED</span></div>)}</section>
      <section className="road-impact"><div className="section-title">DEMO ROAD IMPACT</div>{summary.roads.filter(road => plan.avoid_road_ids.includes(road.id)).map(road => <div key={road.id}><span><strong>{road.name}</strong><small>{road.status === "closed" ? "DEMO CLOSURE" : "DEMO CLOSES AT"}</small></span>{road.status === "closed" ? <Status tone="critical">CLOSED</Status> : <b>{clock(road.closes_at)}</b>}</div>)}</section></div>
    <div className="evidence-note"><span>DEMO PLAN</span>{deadline ? `${plan.zone.name} → ${route.kind} ${route.id} → depart ${clock(deadline)} → ${route.destination.name} → corridor access until ${clock(route.access_until)}.` : `${plan.zone.name} has no evacuation action in this snapshot.`}</div>
    <div className="capacity-risk"><span>DEMO CAPACITY</span><strong>Unassigned: {number(summary.unassigned_population)} people</strong><strong>Assignable capacity: {number(summary.assignable_capacity)}</strong></div>
  </div>;
}

function SafeSites({ summary }: { summary: Summary }) {
  const [filter, setFilter] = useState<Site["kind"] | null>(null);
  const [capacityFound, setCapacityFound] = useState(false);
  const [reviewed, setReviewed] = useState<string | null>(null);
  const toggle = (kind: Site["kind"]) => setFilter(current => current === kind ? null : kind);
  return <div className="safe-sites-page">
    <div className="page-intro"><div><div className="section-kicker">DEMO CAPACITY & ASSIGNMENT</div><div className="page-title">SAFE SITES & CAPACITY</div><p>Demo inventory only. No site has been authority verified.</p></div><div className="site-filters" aria-label="Filter safe sites">
      <button className={filter === "shelter" ? "active" : ""} type="button" onClick={() => toggle("shelter")}>DEMO SHELTER</button><button className={filter === "facility" ? "active" : ""} type="button" onClick={() => toggle("facility")}>FACILITY</button><button className={filter === "candidate" ? "active" : ""} type="button" onClick={() => toggle("candidate")}>CANDIDATE</button>
    </div></div>
    <section className="capacity-deficit"><div><span>DEMO PRIMARY ASSIGNMENTS</span><strong>{number(summary.unassigned_population)} people remain unassigned. {number(summary.assignable_capacity)} demo shelter places.</strong></div>
      {capacityFound ? <div className="capacity-result"><span>UNREVIEWED FACILITIES ARE EXCLUDED</span><strong>ADDITIONAL SAFE CAPACITY: UNKNOWN</strong></div> : <Button variant="secondary" onClick={() => setCapacityFound(true)}>REVIEW CAPACITY</Button>}
    </section>
    <div className="safe-site-list">{summary.sites.filter(site => !filter || site.kind === filter).map(site => <section className={`safe-site-card ${site.kind === "shelter" ? "verified" : site.kind}-site`} key={site.id}>
      <div className="site-card-head"><span className={`site-symbol ${site.kind === "candidate" ? "candidate-symbol" : "building-symbol"}`}>{site.id}</span><div><strong>{site.name}</strong><small>{site.kind === "shelter" ? "DEMO SHELTER" : `UNREVIEWED ${site.kind.toUpperCase()}`}</small></div><Status tone={site.assignable_in_demo ? "cyan" : "warning"}>{site.assignable_in_demo ? "DEMO ONLY" : "REQUIRES REVIEW"}</Status></div>
      {site.kind === "shelter" ? <><div className="site-metrics three"><div><span>DEMO CAPACITY</span><strong>{site.capacity === null ? "UNKNOWN" : number(site.capacity)}</strong></div><div><span>PRIMARY ASSIGNED</span><strong>{number(site.assigned_population)}</strong></div><div><span>UNRESERVED</span><strong>{site.available_capacity === null ? "UNKNOWN" : number(site.available_capacity)}</strong></div></div>
        <div className="site-capacity-bar verified"><span style={{ width: `${site.capacity ? site.assigned_population / site.capacity * 100 : 0}%` }} /></div><div className="site-access"><VerifiedIcon /><strong>DEMO ALLOCATION ONLY</strong><span>BACKUP PREVIEWS DO NOT RESERVE CAPACITY</span></div></>
        : site.kind === "facility" ? <><div className="site-metrics four"><div><span>FLOOD PROBABILITY</span><strong>UNKNOWN</strong></div><div><span>ELEVATION CLEARANCE</span><strong>UNKNOWN</strong></div><div><span>ROAD ACCESS</span><strong>UNASSESSED</strong></div><div><span>DEMO CAPACITY</span><strong>{site.capacity === null ? "UNKNOWN" : `~${number(site.capacity)}`}</strong></div></div><div className="site-note">Illustrative public facility. Excluded from evacuation assignments.</div></>
        : <><div className="site-metrics candidate-metrics"><div><span>DEMO ELEVATION</span><strong>{site.elevation_m === null ? "UNKNOWN" : level(site.elevation_m)}</strong></div><div><span>FLOOD SURFACE</span><strong>UNKNOWN</strong></div><div><span>CLEARANCE</span><strong>UNKNOWN</strong></div><div><span>FLOOD PROBABILITY</span><strong>UNKNOWN</strong></div><div><span>ROAD ACCESS</span><strong>UNKNOWN</strong></div><div><span>DEMO USABLE AREA</span><strong>{site.usable_area_m2 === null ? "UNKNOWN" : `~${number(site.usable_area_m2)}m²`}</strong></div></div><div className="candidate-actions"><span>Candidate only • not approved for assignment</span><Button variant="secondary" onClick={() => setReviewed(site.id)}>{reviewed === site.id ? "DEMO ONLY • NOT SUBMITTED" : "PREVIEW SITE REVIEW"}</Button></div></>}
    </section>)}</div>
  </div>;
}

function AdvisoryPreview({ summary, plan, route, onClose }: { summary: Summary; plan: Plan; route: Route; onClose: () => void }) {
  const [previewed, setPreviewed] = useState(false);
  const dialog = useRef<HTMLElement>(null);
  const isPrepare = plan.zone.severity !== "critical";
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    return () => prior?.focus();
  }, []);
  return <div className="advisory-overlay" role="presentation"><section ref={dialog} tabIndex={-1} className="advisory-preview" role="dialog" aria-modal="true" aria-label="Demo flood advisory preview" onKeyDown={event => {
    if (event.key === "Escape") onClose();
    if (event.key === "Tab") {
      const buttons = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>("button") || []);
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      if (event.shiftKey && index <= 0) { event.preventDefault(); buttons[buttons.length - 1]?.focus(); }
      else if (!event.shiftKey && (index === -1 || index === buttons.length - 1)) { event.preventDefault(); buttons[0]?.focus(); }
    }
  }}>
    {previewed ? <div className="advisory-issued"><span className="advisory-check">✓</span><div className="section-kicker">DEMO PREVIEW COMPLETE</div><div className="advisory-title">{plan.zone.name} • NOTHING SENT</div><p>No SMS, public-address message, field-team notification, or review request was sent or queued.</p><Button onClick={onClose}>CLOSE PREVIEW</Button></div>
      : <><div className="advisory-head"><div><div className="section-kicker">DEMO ONLY • NO DELIVERY</div><div className="advisory-title">{isPrepare ? "PRE-EVACUATION NOTICE" : "FLOOD EVACUATION ALERT"}</div></div><Status tone={isPrepare ? "warning" : "critical"}>{isPrepare ? "PREPARE" : "URGENT"}</Status></div>
        <div className="advisory-zone">{plan.zone.name} • {route.kind.toUpperCase()} {route.id}</div><div className="advisory-deadline">{isPrepare ? "Prepare to leave by" : "Leave before"} <strong>{time(deadlineFor(plan.zone, route), summary.timezone)}</strong></div>
        <div className="advisory-block"><span>DEMO DESTINATION</span><strong>{route.destination.name}</strong></div><div className="advisory-block"><span>VIA</span><strong>{route.stops.slice(1).join(" → ")}</strong></div>
        <div className="advisory-avoid"><span>DO NOT USE</span>{summary.roads.filter(road => plan.avoid_road_ids.includes(road.id)).map(road => <strong key={road.id}>{road.name}</strong>)}</div>
        <div className="advisory-actions"><Button onClick={() => setPreviewed(true)}>SIMULATE PREVIEW <ArrowIcon /></Button><Button variant="secondary" onClick={onClose}>CANCEL</Button></div></>}
  </section></div>;
}

export default function App() {
  const [page, setPage] = useState<Page>("command");
  const [showAdvisory, setShowAdvisory] = useState(false);
  const replay = useReplay();
  const data = replay.data, route = replay.route;
  const navigate = (next: Page) => { setPage(next); setShowAdvisory(false); };
  const errorTitles: Record<string, string> = { ZONE_NOT_FOUND: "ZONE NOT FOUND", PLAN_UNAVAILABLE: "PLAN UNAVAILABLE", BACKEND_UNAVAILABLE: "BACKEND UNAVAILABLE" };
  return <>
    <AppShell page={page} setPage={navigate} summary={data?.summary} unavailable={Boolean(replay.error)}>
      {data && route && !replay.error && <EmergencyStrip summary={data.summary} zone={data.plan.zone} route={route} onView={() => navigate("evacuation")} />}
      <div className="page-content">
        {replay.loading ? <section className="plan-summary" role="status" aria-live="polite"><div><div className="section-title">LOADING DEMO REPLAY</div><p>Fetching one consistent scenario and zone plan…</p></div></section>
          : replay.error || !data || !route ? <section className="plan-summary" role="alert"><div><div className="section-title">{errorTitles[replay.error?.code || ""] || "REPLAY UNAVAILABLE"}</div><p>{replay.error?.message || "No plan is available."}</p><div className="actions"><Button onClick={replay.retry}>RETRY</Button>{data && replay.selectedRoute === "backup" && !data.plan.backup_route && <Button variant="secondary" onClick={() => replay.setSelectedRoute("primary")}>USE PRIMARY ROUTE</Button>}<Button variant="secondary" onClick={replay.reset}>RESET DEMO SELECTION</Button></div></div></section>
          : <>
            {page === "command" && <CommandCenter {...data} route={route} setPage={navigate} selectZone={replay.setSelectedZone} setFrame={replay.setFrameId} selectRoute={replay.setSelectedRoute} openAdvisory={() => setShowAdvisory(true)} />}
            {page === "evacuation" && <Evacuation {...data} route={route} selectZone={replay.setSelectedZone} selectRoute={replay.setSelectedRoute} openAdvisory={() => setShowAdvisory(true)} />}
            {page === "flood" && <FloodIntelligence {...data} route={route} />}
            {page === "shelters" && <SafeSites summary={data.summary} />}
            <p className="site-note">{data.summary.disclaimer}</p>
          </>}
      </div>
    </AppShell>
    {showAdvisory && data && route && !replay.error && !replay.loading && <AdvisoryPreview summary={data.summary} plan={data.plan} route={route} onClose={() => setShowAdvisory(false)} />}
  </>;
}
