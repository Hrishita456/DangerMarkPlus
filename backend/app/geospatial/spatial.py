from pyproj import CRS, Transformer
from shapely.geometry import mapping
from shapely.ops import transform


def metric_crs(value):
    crs = CRS.from_user_input(value)
    if not crs.is_projected or any(axis.unit_name != "metre" for axis in crs.axis_info):
        raise ValueError("Analysis CRS must be projected with metre units")
    return crs


def project(geometry, source, target):
    return transform(Transformer.from_crs(source, target, always_xy=True).transform, geometry)


def feature(geometry, properties, crs):
    web = project(geometry, crs, "EPSG:4326")
    if not web.is_empty:
        west, south, east, north = web.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("Invalid longitude/latitude output")
    return {"type": "Feature", "geometry": mapping(web), "properties": properties}


def collection(features):
    return {"type": "FeatureCollection", "features": features}
