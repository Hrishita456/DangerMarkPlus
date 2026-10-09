from collections import Counter
from app.geospatial.spatial import collection, project
from shapely.geometry import shape
from .assignment import assign
from .deadlines import deadline
from .priority import score
from .routing import Network
from .sites import prepare_sites, site_feature

VERSION='phase4-1.0.1'
ASSUMPTIONS=[
    'Candidate destinations are not verified shelters; building access, opening, usable capacity and actual safety require verification.',
    'Plans are conditional on the Phase 3 scenario, historical OSM and assumed vehicle speeds; not operational evacuation instructions.',
    'Locality buffer population estimates overlap and are not evacuation demand. Demand remains null unless supplied explicitly.',
    'Unknown capacity permits provisional destination assignment, not a claim of sufficient places. Known capacities are reserved only against explicit demands.',
    'Assignment is deterministic greedy, ordered by pre-assignment risk then locality ID; a configured reuse penalty disperses provisional assignments.',
    'Primary route minimizes travel time for each candidate; destination ranking also considers verification, capacity and reuse.',
    'Backup removes all primary network node-pairs in both directions and mapped primary structure way IDs. Endpoint connectors remain shared and unsurveyed.',
    'Static flood evidence does not provide closure times; absent route-specific times produce null departure deadlines.',
    'Known capacity reservations cover simultaneous primary assignments only; backup uses the same site and does not double-reserve.',
    'Individual vehicle travel is not total evacuation duration: no fleet capacity, loading, congestion or repeated shuttles are modelled.']


def plan_all(graph, sites_frame, flood, known_area, localities, impacts, summary, config, crs):
    network=Network(graph,impacts,config,crs)
    known_edge_ids={f'{u}:{v}:{k}' for u,v,k in graph.edges(keys=True)}
    if set(config.closure_times)-known_edge_ids: raise ValueError('Closure schedule references unknown road edges')
    all_ids={f['properties']['locality_id'] for f in localities['features']}
    if set(config.locality_demands_people)-all_ids: raise ValueError('Demand input references unknown locality')
    sites=prepare_sites(sites_frame,network,flood,known_area,config)
    eligible=[site for site in sites if site['properties']['suitability']=='eligible_candidate']
    affected=[f for f in localities['features'] if f['properties']['flood_severity']!='safe' or
              f['properties']['accessibility']!='accessible' or (f['properties']['approximate_population_exposure']['exposed_population'] or 0)>0]
    affected.sort(key=lambda f:(-score(f['properties'],config)['score'],f['properties']['locality_id']))
    plans=[]
    for item in affected:
        locality=item['properties'];lid=locality['locality_id']
        demand=config.locality_demands_people.get(lid)
        point=project(shape(item['geometry']),'EPSG:4326',crs)
        origin,attachment_reason=network.attach(point,flood,known_area,preferred=locality.get('snapped_node_id'))
        candidates=[]
        if origin:
            for site in eligible:
                route=network.route(origin,site['attachment'],summary['replay_at'])
                if route: candidates.append((site,route))
        selected,primary,capacity,outcome,ranking=None,None,'unknown',None,[]
        if not eligible: outcome='no_safe_site'
        elif not candidates: outcome='no_safe_route'
        else: selected,primary,capacity,outcome,ranking=assign(candidates,demand,lid,config)
        backup=network.backup(origin,selected['attachment'],primary,summary['replay_at']) if primary else None
        timing=deadline(primary,summary['replay_at'],config)
        outcomes=[outcome] if outcome else []
        if capacity=='unknown' and 'capacity_unknown' not in outcomes: outcomes.append('capacity_unknown')
        if not backup: outcomes.append('backup_unavailable')
        reasons=[attachment_reason] if attachment_reason else []
        if outcome: reasons.append(outcome)
        if selected: reasons.append('Lowest configured ranking score among reachable, capacity-assignable candidates at this assignment step.')
        if demand is None: reasons.append('Evacuation demand unknown; overlapping population buffers are not promoted into assigned headcounts.')
        plans.append({'locality':locality,'demand_people':demand,'demand_source':'configured_planning_input' if demand else 'unknown',
            'provenance':{'run_id':summary.get('run_id'),'planning_algorithm':VERSION,
                'consequence_algorithm':summary.get('algorithm_version'),'bundle_sha256':summary.get('bundle_sha256'),
                'replay_at':summary['replay_at'],'flood_source':summary.get('source'),
                'operationally_validated':False},
            'priority':score(locality,config,primary is not None,capacity,timing['urgency']),
            'selected_destination':site_feature(selected,crs) if selected else None,
            'capacity_status':capacity,'primary_route':primary,'backup_route':backup,
            'backup_status':'available' if backup else 'unavailable',
            'backup_reason':'Network physical node-pairs and mapped structure IDs are disjoint; access connectors remain shared.' if backup else 'No network-edge-independent alternative to the same destination under the permitted graph and closure constraints.',
            'deadline':timing,'backup_deadline':deadline(backup,summary['replay_at'],config) if backup else None,
            'outcomes':outcomes,'feasible_destinations':ranking,'reasons':reasons,'assumptions':ASSUMPTIONS})
    # Destination snapshots show final aggregate reservations, not intermediate ledger values.
    final_sites={site['properties']['id']:site for site in sites}
    for plan in plans:
        if plan['selected_destination']:
            plan['selected_destination']=site_feature(final_sites[plan['selected_destination']['properties']['id']],crs)
    counts={'affected_localities':len(plans),'feasible_plans':sum(p['primary_route'] is not None for p in plans),
            'backup_routes':sum(p['backup_route'] is not None for p in plans),
            'capacity_unknown':sum(p['capacity_status']=='unknown' for p in plans),
            'candidate_sites':len(sites),'eligible_candidate_sites':len(eligible)}
    for outcome in ['no_safe_route','no_safe_site','insufficient_known_capacity','backup_unavailable']:
        counts[outcome]=sum(outcome in p['outcomes'] for p in plans)
    return {'counts':counts,'plans':plans,'safe_sites':collection([site_feature(site,crs) for site in sites]),'assumptions':ASSUMPTIONS}
