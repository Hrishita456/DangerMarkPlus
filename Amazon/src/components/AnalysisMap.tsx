import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import type { AnalysisData, LocalityPlan } from "../types/analysis";
export default function AnalysisMap({data, plan, kind, onSelect}: {data: AnalysisData; plan?: LocalityPlan; kind: "primary" | "backup"; onSelect: (id: string) => void}) {
  const container = useRef<HTMLDivElement>(null);
  const selection = useRef(onSelect); selection.current = onSelect;
  const [tileError, setTileError] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    const map = L.map(container.current, {scrollWheelZoom: false, preferCanvas: true}).setView([28.65,77.25], 12);
    const tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution: "&copy; OpenStreetMap contributors", maxZoom: 18}).addTo(map);
    tiles.on("tileerror", () => setTileError(true));
    const tooltip = (text: string) => {const span = document.createElement("span"); span.textContent = text; return span;};
    const flood = L.geoJSON(data.flood, {style: {color: "#3B82D6", fillColor: "#8DBBEA", fillOpacity: .28, weight: 1}}).addTo(map);
    const closureRoads = {...data.roads, features: data.roads.features.filter(f => f.properties.status === "closure_candidate")};
    L.geoJSON(closureRoads, {style: {color: "#D6343B", weight: 3, dashArray: "8 7"}, onEachFeature: (f, layer) => layer.bindTooltip(tooltip(`${f.properties.name || "Unnamed road"} · closure candidate`))}).addTo(map);
    const ids = new Set(data.planning.plans.map(p => p.locality.locality_id));
    const affectedPoints = {...data.localities, features: data.localities.features.filter(f => ids.has(f.properties.locality_id))};
    const points = L.geoJSON(affectedPoints, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {radius: f.properties.locality_id === plan?.locality.locality_id ? 9 : 6, color: "#162E4F", fillColor: "#E9A035", fillOpacity: 1}),
      onEachFeature: (f, layer) => {layer.bindTooltip(tooltip(f.properties.name)); layer.on("click", () => selection.current(f.properties.locality_id));},
    }).addTo(map);
    for (const routeKind of ["primary", "backup"] as const) {
      const route = plan?.[routeKind === "primary" ? "primary_route" : "backup_route"];
      if (route) L.geoJSON(route.geometry, {style: {color: routeKind === "primary" ? "#2E9E72" : "#1F5FBF", weight: kind === routeKind ? 7 : 3, opacity: kind === routeKind ? 1 : .45, dashArray: routeKind === "backup" ? "10 7" : undefined}})
        .bindTooltip(tooltip(`${routeKind} · ${route.distance_km.toFixed(2)} km · estimated ${route.travel_minutes.toFixed(1)} min`)).addTo(map);
    }
    if (plan?.selected_destination) L.geoJSON(plan.selected_destination, {pointToLayer: (_f, ll) => L.circleMarker(ll, {radius: 9, color: "#2E9E72", fillColor: "#fff", fillOpacity: 1})})
      .bindTooltip(tooltip(`${plan.selected_destination.properties.name || plan.selected_destination.properties.id} · candidate · capacity ${plan.capacity_status}`)).addTo(map);
    const selected = plan?.[kind === "primary" ? "primary_route" : "backup_route"];
    const bounds = selected ? L.geoJSON(selected.geometry).getBounds() : flood.getBounds().isValid() ? flood.getBounds() : points.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds.pad(.25), {maxZoom: 16});
    const observer = new ResizeObserver(() => map.invalidateSize()); observer.observe(container.current);
    return () => {observer.disconnect(); map.remove();};
  }, [data, plan, kind]);
  return <div className="map-wrap" style={{isolation:"isolate"}}>
    <div className="leaflet-map" ref={container} aria-label="Analysis map: backend flood, locality, road and route geometry" />
    <div className="map-key"><span><i className="key-primary"/>PRIMARY</span><span><i className="key-backup"/>BACKUP</span><span><i className="key-closed"/>CLOSURE CANDIDATES</span><span><i className="key-flood"/>ASSUMED FLOOD</span></div>
    {tileError && <div className="site-note" role="status">Basemap tiles unavailable; backend overlays remain visible.</div>}
    {!data.flood.features.length && <div className="site-note">No flood geometry returned for this run.</div>}
  </div>;
}
