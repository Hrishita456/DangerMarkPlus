import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import type { Plan, Position, RouteKind, Summary } from "../types/replay";
import { number, time } from "../api/format";

const latLng = (point: Position): L.LatLngTuple => [point.latitude, point.longitude];

export default function EvacuationMap({ summary, plan, selectedRoute }: {
  summary: Summary; plan: Plan; selectedRoute: RouteKind;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [candidateId, setCandidateId] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const candidate = summary.sites.find(site => site.id === candidateId);

  useEffect(() => {
    if (!container.current) return;
    const map = L.map(container.current, {
      center: latLng(plan.zone.position), zoom: 13, scrollWheelZoom: false,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors", maxZoom: 18,
    }).addTo(map);
    // This is an illustrative Figma footprint, not a modelled flood extent.
    L.polygon(summary.illustrative_flood_polygon.map(latLng), {
      color: "#3B82D6", fillColor: "#8DBBEA", fillOpacity: 0.28, weight: 1,
    }).bindTooltip("Illustrative demo footprint — no safety inference").addTo(map);
    const tooltip = (text: string) => { const content = document.createElement("span"); content.textContent = text; return content; };
    const routes = [plan.primary_route, plan.backup_route].filter(route => route !== null);
    for (const route of routes) {
      L.polyline(route.geometry.map(latLng), {
        color: route.kind === "primary" ? "#2E9E72" : "#1F5FBF",
        weight: route.kind === selectedRoute ? 7 : 4,
        opacity: route.kind === selectedRoute ? 0.95 : 0.5,
        dashArray: route.kind === "backup" ? "10 7" : undefined,
      }).bindTooltip(tooltip(`Demo ${route.kind} ${route.id} — illustrative geometry`)).addTo(map);
    }
    for (const road of summary.roads.filter(road => plan.avoid_road_ids.includes(road.id))) {
      L.polyline(road.geometry.map(latLng), { color: "#D6343B", weight: 6, dashArray: "8 7" })
        .bindTooltip(tooltip(`${road.name} • DEMO ${road.status === "closed" ? "closed" : `closes ${time(road.closes_at, summary.timezone)}`}`)).addTo(map);
    }
    const marker = (position: Position, text: string, tone: string, kind = "") => {
      // Use DOM text rather than injecting API-supplied strings into HTML.
      const content = document.createElement("span");
      content.className = `operational-marker ${tone} ${kind}`;
      const iconPaths: Record<string, string[]> = {
        verified: ["M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6l8-3Z", "m8 12 2.5 2.5 5.5-5.5"],
        facility: ["M5 21V5h10v16M15 10h4v11M8 8h4M8 12h4M8 16h4"],
        candidate: ["m3 20 8-15 4 8 2-4 4 11H3Z", "M9 16h6"],
      };
      if (iconPaths[kind]) {
        const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        icon.setAttribute("viewBox", "0 0 24 24");
        icon.setAttribute("aria-hidden", "true");
        for (const shape of iconPaths[kind]) {
          const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
          path.setAttribute("d", shape);
          icon.append(path);
        }
        content.append(icon);
      }
      const label = document.createElement("b");
      label.textContent = text;
      content.append(label);
      return L.marker(latLng(position), {
        icon: L.divIcon({ className: "operational-marker-shell", html: content, iconSize: [52, 32], iconAnchor: [26, 16] }),
      }).addTo(map);
    };
    marker(plan.zone.position, `Z${plan.zone.id}`, plan.zone.severity === "high" ? "warning" : plan.zone.severity)
      .bindTooltip(tooltip(`${plan.zone.name} • ${number(plan.zone.population)} people (demo)`), { permanent: true, direction: "bottom", offset: [0, 10] });
    for (const site of summary.sites) {
      const destination = routes.some(route => route.destination_id === site.id);
      const point = marker(site.position, site.id, site.assignable_in_demo ? "safe" : "warning", site.kind === "shelter" ? "verified" : site.kind);
      point.bindTooltip(tooltip(`${site.name} • ${site.assignable_in_demo ? "Demo shelter, not verified" : "Unreviewed demo site"}`), {
        permanent: destination, direction: "top", offset: [0, -10],
      });
      if (site.kind === "candidate") point.on("click", () => { setCandidateId(site.id); setReviewed(false); });
    }
    map.fitBounds(L.latLngBounds(routes.flatMap(route => route.geometry.map(latLng))).pad(0.2));
    return () => { map.remove(); };
  }, [summary, plan, selectedRoute]);

  return <div className="map-wrap" style={{ isolation: "isolate" }}>
    <div className="leaflet-map" ref={container} aria-label={`Illustrative demo evacuation map for ${plan.zone.name}`} />
    <div className="map-key">
      <span><i className="key-primary" /> PRIMARY</span><span><i className="key-backup" /> BACKUP</span>
      <span><i className="key-closed" /> ROAD WATCH</span><span><i className="key-flood" /> DEMO FOOTPRINT</span>
    </div>
    {candidate && <aside className="candidate-map-detail">
      <button className="candidate-close" type="button" onClick={() => setCandidateId(null)} aria-label="Close candidate site details">×</button>
      <span>CANDIDATE {candidate.id} • DEMO ONLY</span><strong>REQUIRES AUTHORITY VERIFICATION</strong>
      <div><span>ELEVATION CLEARANCE</span><b>UNKNOWN</b></div>
      <div><span>FLOOD PROBABILITY</span><b>UNKNOWN</b></div>
      <div><span>ROAD ACCESS</span><b>NOT ASSESSED</b></div>
      <div><span>DEMO USABLE AREA</span><b>{candidate.usable_area_m2 === null ? "UNKNOWN" : `~${number(candidate.usable_area_m2)}m²`}</b></div>
      <button className="button button-secondary" type="button" onClick={() => setReviewed(true)}>{reviewed ? "DEMO ONLY • NOT SUBMITTED" : "PREVIEW SITE REVIEW"}</button>
    </aside>}
  </div>;
}
