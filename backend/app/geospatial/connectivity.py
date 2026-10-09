from collections import deque
import networkx as nx
from shapely.geometry import Point
from shapely.strtree import STRtree


def reachable(graph, gateways, disabled):
    """Directed reverse search: nodes with any outgoing path to a gateway."""
    seen = set(gateways)
    pending = deque(gateways)
    while pending:
        target = pending.popleft()
        for source, _, key in graph.in_edges(target, keys=True):
            if (source, target, key) not in disabled and source not in seen:
                seen.add(source)
                pending.append(source)
    return seen


def classify_access(node, baseline, optimistic, cautious, nearby_affected):
    if node is None or node not in baseline:
        return "unknown", "No baseline path to a configured gateway or no road node within snap limit."
    if node not in optimistic:
        return "isolated", "Baseline gateway access lost after removing closure candidates."
    if node not in cautious:
        return "at_risk_of_isolation", "Gateway access depends on an uncertain structure or road outside known coverage."
    if nearby_affected:
        return "degraded_access", "Gateway remains reachable, but roads near this locality are affected."
    return "accessible", "Directed gateway path remains under both edge-removal assumptions."


class Connectivity:
    def __init__(self, graph, boundary, flood, known_area, closed, uncertain, thresholds):
        self.nodes = list(graph.nodes)
        self.points = [Point(graph.nodes[n]['x'], graph.nodes[n]['y']) for n in self.nodes]
        self.tree = STRtree(self.points)
        largest = max(nx.weakly_connected_components(graph), key=len) if graph else set()
        gateways = [n for n, p in zip(self.nodes,self.points)
                    if n in largest and boundary.covers(p) and known_area.covers(p)
                    and p.distance(boundary.boundary) <= thresholds.gateway_ring_m
                    and (flood.is_empty or p.distance(flood) > thresholds.gateway_flood_clearance_m)]
        self.gateways = gateways
        self.baseline = reachable(graph, gateways, set())
        self.optimistic = reachable(graph, gateways, closed)
        self.cautious = reachable(graph, gateways, closed | uncertain)
        self.snap_max_m = thresholds.snap_max_m

    def locality(self, point, nearby_affected):
        idx = self.tree.nearest(point) if self.nodes else None
        distance = point.distance(self.points[idx]) if idx is not None else None
        node = self.nodes[idx] if distance is not None and distance <= self.snap_max_m else None
        status, reason = classify_access(node, self.baseline, self.optimistic, self.cautious, nearby_affected)
        return {"accessibility": status, "access_reason": reason,
                "snapped_node_id": str(node) if node is not None else None,
                "snap_distance_m": round(distance,1) if distance is not None else None}
