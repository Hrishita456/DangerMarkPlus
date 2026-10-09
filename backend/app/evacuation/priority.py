def score(locality, config, route_available=True, capacity='sufficient', urgency='unknown'):
    weights=config.priority
    parts={'severity':weights.severity[locality['flood_severity']],
           'access':weights.access[locality['accessibility']]}
    population=locality['approximate_population_exposure']['exposed_population']
    parts['approximate_buffer_exposure']=min(weights.exposure_cap,(population or 0)/1000*weights.exposure_per_1000)
    if not route_available: parts['no_feasible_plan']=weights.no_route
    if capacity=='unknown': parts['capacity_unknown']=weights.capacity_unknown
    if urgency=='elapsed': parts['deadline_elapsed']=weights.deadline_elapsed
    if urgency=='soon': parts['deadline_soon']=weights.deadline_soon
    total=sum(parts.values())
    level='critical' if total>=weights.critical_threshold else 'high' if total>=weights.high_threshold else 'moderate' if total>=weights.moderate_threshold else 'low'
    return {'score':round(total,2),'level':level,'contributions':parts,
            'reasons':[f'{name}: +{value:g}' for name,value in parts.items() if value],
            'note':'Approximate buffer exposure is a risk indicator, not evacuation demand. Unknown timing adds no invented urgency.'}
