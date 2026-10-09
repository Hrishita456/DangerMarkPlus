import math
from app.geospatial.spatial import feature


def prepare_sites(frame, network, flood, known_area, config):
    sites=[]
    for _,row in frame.sort_values('id').iterrows():
        point=row.geometry
        if point.geom_type!='Point' or not point.is_valid: raise ValueError('Candidate sites require valid representative points')
        capacity=row.get('capacity')
        if capacity is not None and isinstance(capacity,float) and math.isnan(capacity): capacity=None
        if capacity is not None and (not math.isfinite(capacity) or capacity<0 or int(capacity)!=capacity):
            raise ValueError('Invalid candidate capacity')
        props={key:row.get(key) for key in ['id','name','type','source','verification_status','capacity_source']}
        props={key:(None if isinstance(value,float) and math.isnan(value) else value) for key,value in props.items()}
        props['capacity']=int(capacity) if capacity is not None else None
        clearance=point.distance(flood) if not flood.is_empty else None
        reasons=[]
        if row['type'] not in config.eligible_types: reasons.append('Facility type is not enabled for this planning mode.')
        if not known_area.covers(point): reasons.append('Site is outside known scenario coverage.')
        if not flood.is_empty and clearance<config.site_clearance_m: reasons.append('Site fails configured flood clearance.')
        nearby=network.edge_tree.query(point.buffer(config.road_attachment_tolerance_m),predicate='intersects')
        if any(network.edge_statuses[i] in config.excluded_road_statuses for i in nearby):
            reasons.append('Site is on or immediately beside an excluded road segment.')
        attachment,reason=network.attach(point,flood,known_area)
        if reason: reasons.append(reason)
        props.update({'suitability':'eligible_candidate' if not reasons else 'ineligible',
                      'flood_clearance_m':round(clearance,1) if clearance is not None else None,
                      'reasons':reasons or ['Outside flood clearance, known coverage, permitted baseline attachment; still unverified.'],
                      'assigned_locality_ids':[], 'reserved_people':0, 'available_capacity':int(capacity) if capacity is not None else None,
                      'capacity_status':'unknown' if capacity is None else 'unassigned',
                      'attachment_distance_m':round(attachment['distance_m'],1) if attachment else None})
        sites.append({'properties':props,'geometry':point,'attachment':attachment})
    return sites


def site_feature(site, crs):
    return feature(site['geometry'],site['properties'].copy(),crs)
