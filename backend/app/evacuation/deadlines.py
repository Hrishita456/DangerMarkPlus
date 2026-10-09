from datetime import datetime, timedelta


def deadline(route, replay_at, config):
    empty = {'deadline_status':'unavailable','latest_departure':None,'latest_vehicle_departure':None,
             'urgency':'unknown','limiting_edge_id':None,
             'reasons':['No route-specific closure times; static flood extent cannot establish a departure deadline.']}
    if route is None:
        return {**empty, 'reasons':['No feasible route; no departure deadline can be calculated.']}
    constraints=[]
    for edge, minutes in route['edge_exit_minutes'].items():
        if edge in config.closure_times:
            vehicle = config.closure_times[edge] - timedelta(minutes=minutes + config.safety_minutes)
            constraints.append((vehicle - timedelta(minutes=config.mobilization_minutes), vehicle, edge))
    if not constraints:
        return empty
    start, vehicle, edge=min(constraints)
    now=datetime.fromisoformat(replay_at) if isinstance(replay_at,str) else replay_at
    remaining=(start-now).total_seconds()/60
    return {'deadline_status':'scenario_estimate' if config.closure_time_source=='scenario_assumption' else 'observed_constraint_estimate',
            'latest_departure':start.isoformat(),'latest_vehicle_departure':vehicle.isoformat(),
            'urgency':'elapsed' if remaining <= 0 else 'soon' if remaining <= config.priority.urgency_minutes else 'later',
            'limiting_edge_id':edge,'reasons':[
                'Latest departure denotes initiation of mobilization; vehicle departure follows preparation.',
                'Minimum of closure time minus cumulative travel through the threatened edge, safety margin and mobilization.',
                'Only supplied edge constraints are evaluated; untimed edges and destination future safety remain unknown.']}
