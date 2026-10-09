def capacity_status(site, demand):
    capacity=site['properties']['available_capacity']
    if capacity is None: return 'unknown'
    if capacity==0: return 'insufficient'
    if demand is None: return 'unknown'
    return 'sufficient' if demand<=capacity else 'insufficient'


def rank(site, route, demand, config):
    props=site['properties'];weights=config.ranking
    parts={'travel_minutes':route['travel_minutes']*weights.minutes,
           'distance':route['distance_km']*weights.kilometres,
           'verification':0 if props['verification_status']=='verified' else weights.unverified,
           'capacity':weights.unknown_capacity if capacity_status(site,demand)=='unknown' else 0,
           'previous_assignments':len(props['assigned_locality_ids'])*weights.prior_assignment}
    return {'score':round(sum(parts.values()),6),'components':parts,
            'reasons':[f'{key}: {value:g}' for key,value in parts.items()],
            'capacity_status':capacity_status(site,demand)}


def assign(candidates, demand, locality_id, config):
    ranked=[]
    for site,route in candidates:
        rating=rank(site,route,demand,config)
        # Unknown demand must never silently consume or overbook known capacity.
        eligible=rating['capacity_status']!='insufficient' and not (demand is None and site['properties']['capacity'] is not None)
        ranked.append((rating['score'],site['properties']['id'],site,route,rating,eligible))
    ranked.sort(key=lambda item:(item[0],item[1]))
    choices=[item for item in ranked if item[-1]]
    descriptions=[{'site_id':item[1],**item[4],'assignable':item[-1]} for item in ranked]
    if not choices:
        outcome='capacity_unknown' if demand is None and candidates else 'insufficient_known_capacity'
        return None,None,'unknown' if demand is None else 'insufficient',outcome,descriptions
    _,_,site,route,rating,_=choices[0]
    props=site['properties'];props['assigned_locality_ids'].append(locality_id)
    if props['capacity'] is not None:
        props['reserved_people']+=demand
        props['available_capacity']-=demand
    props['capacity_status']=rating['capacity_status']
    return site,route,rating['capacity_status'],None,descriptions
