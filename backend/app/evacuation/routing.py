import math
from datetime import datetime

import networkx as nx
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from app.geospatial.roads import tag_present
from app.geospatial.spatial import feature


def edge_id(u,v,key):
    return f'{u}:{v}:{key}'


def physical_pair(u,v):
    return tuple(sorted((str(u),str(v))))


def values(value):
    if isinstance(value,(tuple,list)): return [str(v) for v in value]
    return [] if value is None else [str(value)]


class Network:
    def __init__(self, graph, impacts, config, crs):
        self.config,self.crs=config,crs
        self.graph=nx.MultiDiGraph()
        self.graph.add_nodes_from(graph.nodes(data=True))
        self.nodes=sorted(graph.nodes,key=str)
        self.node_lookup={str(n):n for n in self.nodes}
        self.points=[Point(graph.nodes[n]['x'],graph.nodes[n]['y']) for n in self.nodes]
        self.tree=STRtree(self.points)
        self.edge_geometries=[];self.edge_statuses=[]
        for u,v,key,data in sorted(graph.edges(keys=True,data=True),key=lambda item:tuple(map(str,item[:3]))):
            eid=edge_id(u,v,key)
            status=impacts.get(eid,{}).get('status','unaffected')
            geometry=data.get('geometry')
            if geometry is None: geometry=LineString([(graph.nodes[u]['x'],graph.nodes[u]['y']),(graph.nodes[v]['x'],graph.nodes[v]['y'])])
            self.edge_geometries.append(geometry);self.edge_statuses.append(status)
            if status in config.excluded_road_statuses or u==v: continue
            length=float(data.get('length',geometry.length))
            speed=data.get('speed_kph')
            try: speed=float(speed)
            except (TypeError,ValueError): speed=0
            speed_source=data.get('speed_source','persisted_speed_assumption')
            if not math.isfinite(speed) or speed<=0:
                classes=values(data.get('highway'))
                speed=min([config.class_speeds_kph.get(c,config.default_speed_kph) for c in classes] or [config.default_speed_kph])
                speed_source='configured_class_default'
            if not math.isfinite(length) or length<=0: raise ValueError(f'Invalid edge length: {eid}')
            minutes=length/(speed*config.speed_factor*1000/60)
            attrs={**data,'edge_id':eid,'geometry':geometry,'minutes':minutes,'length_m':length,
                   'speed_source':speed_source,'pair':physical_pair(u,v),'status':status}
            self.graph.add_edge(u,v,key=key,**attrs)
        self.edge_tree=STRtree(self.edge_geometries)
        self.bridge_pairs={physical_pair(u,v) for u,v in nx.bridges(nx.Graph(self.graph))}
        self.paths_cache={}

    def attach(self, point, flood, known_area, preferred=None):
        if preferred is not None:
            node=self.node_lookup.get(str(preferred))
        else:
            idx=self.tree.nearest(point) if self.nodes else None
            node=self.nodes[idx] if idx is not None else None
        if node is None: return None,'No baseline road node.'
        p=Point(self.graph.nodes[node]['x'],self.graph.nodes[node]['y'])
        distance=point.distance(p)
        connector=LineString([point,p]) if distance else point
        if distance>self.config.snap_max_m: return None,'Baseline road attachment exceeds configured distance.'
        if not known_area.buffer(.01).covers(connector) or connector.intersects(flood):
            return None,'Access connector crosses flood or unknown coverage.'
        if self.graph.degree(node)==0: return None,'Baseline attachment has no permitted road edges.'
        return {'node':node,'point':point,'node_point':p,'distance_m':distance,
                'minutes':distance/(self.config.connector_speed_kph*1000/60)},None

    def paths(self, origin, replay_at, banned_pairs=frozenset(), banned_structures=frozenset()):
        """Earliest arrival with known closure deadlines; no waiting or invented closures."""
        import heapq
        cache_key=(origin['node'],origin['minutes'],str(replay_at),banned_pairs,banned_structures)
        if cache_key in self.paths_cache: return self.paths_cache[cache_key]
        now=datetime.fromisoformat(replay_at) if isinstance(replay_at,str) else replay_at
        distances={origin['node']:origin['minutes']};parents={}
        queue=[(origin['minutes'],str(origin['node']),origin['node'])]
        while queue:
            cost,_,u=heapq.heappop(queue)
            if cost!=distances[u]: continue
            for _,v,key,data in sorted(self.graph.out_edges(u,keys=True,data=True),key=lambda item:(str(item[1]),str(item[2]))):
                if data['pair'] in banned_pairs: continue
                if banned_structures.intersection(values(data.get('osmid'))): continue
                arrival=cost+data['minutes']
                closes=self.config.closure_times.get(data['edge_id'])
                if closes is not None and (closes-now).total_seconds()/60 <= arrival+self.config.mobilization_minutes+self.config.safety_minutes:
                    continue
                if arrival<distances.get(v,float('inf')):
                    distances[v]=arrival;parents[v]=(u,key)
                    heapq.heappush(queue,(arrival,str(v),v))
        result=(distances,parents)
        self.paths_cache[cache_key]=result
        return result

    def route(self, origin, destination, replay_at, banned_pairs=frozenset(), banned_structures=frozenset()):
        distances,parents=self.paths(origin,replay_at,banned_pairs,banned_structures)
        target=destination['node']
        if target not in distances: return None
        nodes=[target];keys=[]
        while nodes[-1]!=origin['node']:
            parent,key=parents[nodes[-1]];nodes.append(parent);keys.append(key)
        nodes.reverse();keys.reverse()
        edges=[self.graph[u][v][key] for u,v,key in zip(nodes,nodes[1:],keys)]
        # A zero-edge connector-only trip is not a verified road evacuation route.
        if not edges: return None
        coordinates=[tuple(origin['point'].coords[0]),tuple(origin['node_point'].coords[0])]
        elapsed=origin['minutes'];exits={};bottlenecks=[];structures=[];names=[]
        for u,v,data in zip(nodes,nodes[1:],edges):
            coords=list(data['geometry'].coords)
            start=Point(self.graph.nodes[u]['x'],self.graph.nodes[u]['y'])
            if start.distance(Point(coords[-1]))<start.distance(Point(coords[0])): coords.reverse()
            coordinates.extend(coords)
            elapsed+=data['minutes'];exits[data['edge_id']]=elapsed
            structural=any(tag_present(data.get(key)) for key in ('bridge','tunnel','layer'))
            if structural: structures.append({'edge_id':data['edge_id'],'reason':'Mapped structure outside excluded flood impacts; deck/portal not field verified.'})
            if data['pair'] in self.bridge_pairs or structural:
                bottlenecks.append({'edge_id':data['edge_id'],'reason':'Undirected graph cut-link' if data['pair'] in self.bridge_pairs else 'Mapped bridge/tunnel/layered structure'})
            for name in values(data.get('name')):
                if name not in names: names.append(name)
        coordinates.extend([tuple(destination['node_point'].coords[0]),tuple(destination['point'].coords[0])])
        cleaned=[coordinates[0]]
        for coord in coordinates[1:]:
            if coord!=cleaned[-1]: cleaned.append(coord)
        geometry=LineString(cleaned)
        connectors=[{'kind':kind,'length_m':round(item['distance_m'],2),'travel_minutes':round(item['minutes'],3),'verification_status':'assumed_unsurveyed'} for kind,item in [('origin',origin),('destination',destination)]]
        return {'geometry':feature(geometry,{'mode':self.config.mode},self.crs),
                'distance_km':round((sum(d['length_m'] for d in edges)+origin['distance_m']+destination['distance_m'])/1000,3),
                'travel_minutes':round(elapsed+destination['minutes'],3),
                'edge_ids':[d['edge_id'] for d in edges],'edge_exit_minutes':exits,
                'road_names':names,'bottlenecks':bottlenecks,'uncertain_structures':structures,
                'connectors':connectors,'assumptions':[
                    'Minimum estimated vehicle travel time on permitted directed edges; no traffic, turn restrictions or fleet/shuttle model.',
                    f'Persisted/class speeds multiplied by {self.config.speed_factor:g}; access connectors assume {self.config.connector_speed_kph:g} km/h.',
                    'Straight access connectors are unsurveyed assumptions; field access and destination availability require verification.']}

    def backup(self, origin, destination, primary, replay_at):
        primary_ids=set(primary['edge_ids']);pairs=set();structures=set()
        for _,_,data in self.graph.edges(data=True):
            if data['edge_id'] in primary_ids:
                pairs.add(data['pair'])
                if any(tag_present(data.get(k)) for k in ('bridge','tunnel','layer')):
                    structures.update(values(data.get('osmid')))
        return self.route(origin,destination,replay_at,frozenset(pairs),frozenset(structures))
