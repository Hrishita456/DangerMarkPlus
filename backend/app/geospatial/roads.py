from shapely.geometry import LineString
from shapely.strtree import STRtree


def tag_present(value):
    values = value if isinstance(value, (list, tuple)) else [value]
    return any(str(v).lower() not in {"none", "nan", "no", "false", "0", ""} for v in values)


def impact(geometry, attrs, flood, known_area, threshold, near_m):
    flooded_length = geometry.intersection(flood).length
    elevated = tag_present(attrs.get("bridge")) or tag_present(attrs.get("tunnel")) or tag_present(attrs.get("layer"))
    if not known_area.buffer(0.01).covers(geometry):
        status, reason = "unknown", "Road leaves known scenario coverage; access is uncertain."
    else:
        status, reason = "unaffected", "No scenario intersection or configured proximity."
    if flooded_length >= threshold:
        status = "uncertain_structure" if elevated else "closure_candidate"
        reason = "Flood intersects a bridge, tunnel or layered road; deck/portal elevation unknown." if elevated else "At-grade road intersects assumed flood by the configured minimum length; precautionary closure candidate, not observed closure."
    elif not flood.is_empty and geometry.distance(flood) <= near_m and status != "unknown":
        status, reason = "near_flood", "Within configured flood proximity; not automatically closed."
    return {"name": attrs.get("name"), "road_class": attrs.get("highway"),
            "length_m": round(geometry.length, 2), "bridge": attrs.get("bridge"),
            "layer": attrs.get("layer"), "tunnel": attrs.get("tunnel"),
            "flood_intersection_length_m": round(flooded_length, 2), "status": status,
            "reason": reason, "confidence": "scenario_dependent_not_field_verified"}


def evaluate_roads(graph, flood, known_area, thresholds):
    records, geometries, closed, uncertain = [], [], set(), set()
    for u, v, key, attrs in graph.edges(keys=True, data=True):
        geometry = attrs.get("geometry")
        if geometry is None:
            geometry = LineString([(graph.nodes[u]['x'], graph.nodes[u]['y']), (graph.nodes[v]['x'], graph.nodes[v]['y'])])
        props = impact(geometry, attrs, flood, known_area, thresholds.closure_intersection_m, thresholds.road_near_m)
        edge = (u,v,key)
        props['edge_id'] = f"{u}:{v}:{key}"
        if props['status'] == 'closure_candidate': closed.add(edge)
        if props['status'] in {'unknown','uncertain_structure'}: uncertain.add(edge)
        records.append(props)
        geometries.append(geometry)
    return records, geometries, closed, uncertain, STRtree(geometries)
