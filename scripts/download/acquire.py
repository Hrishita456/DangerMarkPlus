"""Acquire only bounded pilot inputs. Reuse and verify cached inputs by default.

Run from the repository root: scripts/.venv/bin/python scripts/download/acquire.py
No credentials, GIS GUI, AWS account or runtime backend dependency is required.
"""
import argparse
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (CATALOG, RAW, USER_AGENT, config, read_json, record_acquisition,
                    sha256, verified_existing)
import certifi
import rasterio
from rasterio.windows import Window, from_bounds
import requests
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform

SESSION = requests.Session()
SESSION.headers["User-Agent"] = USER_AGENT


def save_response(response, destination, limit):
    response.raise_for_status()
    declared = int(response.headers.get("Content-Length", 0))
    if declared > limit:
        raise RuntimeError(f"Download exceeds explicit {limit} byte limit: {declared}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    if temporary.exists():
        raise RuntimeError(f"Partial download exists: {temporary}. Inspect it before retrying; never overwrite a running download.")
    total = 0
    next_progress = 32 * 1024 * 1024
    try:
        with temporary.open("xb") as output:
            for chunk in response.iter_content(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise RuntimeError("Download exceeded configured byte limit")
                output.write(chunk)
                if total >= next_progress:
                    print(f"Downloaded {total:,} / {declared or 'unknown'} bytes: {destination.name}", flush=True)
                    next_progress += 32 * 1024 * 1024
        if declared and response.headers.get('Content-Encoding', 'identity') == 'identity' and total != declared:
            raise RuntimeError(f"Incomplete response: expected {declared}, received {total} bytes")
        temporary.replace(destination)
    except Exception:
        # Preserve expensive partial downloads for inspection. A future Range
        # resume must first verify server support and the source ETag.
        raise


def raster_window(dataset_id, source, pilot):
    destination = RAW / source["category"] / source["raw_name"]
    if verified_existing(dataset_id, destination):
        return
    url = source["url"]
    input_path = url
    full_source = None
    local = source['kind'] == 'local_raster'
    remote = {}
    if local:
        full_source = RAW / source['category'] / source['local_source_name']
        if not full_source.exists():
            raise FileNotFoundError(f'User-supplied raster missing: {full_source}; automatic download is disabled')
        if sha256(full_source) != source['expected_local_sha256']:
            raise ValueError('User-supplied source checksum changed; preserve and investigate')
        input_path = str(full_source)
    else:
        # Only a source explicitly configured for full transfer may bypass Range.
        with SESSION.get(url, headers={"Range": "bytes=0-15"}, stream=True, timeout=(30, 300)) as response:
            remote = {key: response.headers.get(key) for key in ("ETag", "Last-Modified", "Content-Range")}
            if response.status_code != 206:
                if response.status_code != 200 or not source.get("allow_full_download"):
                    raise RuntimeError(f"Byte ranges unavailable for {url}: HTTP {response.status_code}")
                full_source = destination.with_name(f"{dataset_id}_full_source.tif")
                if not full_source.exists():
                    print(f"Range unsupported; caching approved full source ({response.headers.get('Content-Length')} bytes)", flush=True)
                    save_response(response, full_source, source["max_download_bytes"])
                elif int(response.headers.get("Content-Length", 0)) not in (0, full_source.stat().st_size):
                    raise RuntimeError("Cached full source size differs from remote source; preserve and investigate")
                input_path = str(full_source)
            else:
                response.raw.read(16)
    print(f"Reading bounded raster window: {dataset_id}", flush=True)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_USERAGENT=USER_AGENT, GDAL_HTTP_CAINFO=certifi.where(),
                      GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(input_path) as src:
            if src.crs.to_epsg() != 4326:
                raise ValueError("This acquisition expects a WGS84 source")
            if src.count != 1 or src.scales != (1.0,) or src.offsets != (0.0,):
                raise ValueError('Expected one unscaled source band; use an explicit adapter for other encodings')
            requested = from_bounds(*pilot["bbox_wgs84"], src.transform)
            # Two source pixels of padding preserve edge contributions during reprojection.
            col, row = math.floor(requested.col_off) - 2, math.floor(requested.row_off) - 2
            right = math.ceil(requested.col_off + requested.width) + 2
            bottom = math.ceil(requested.row_off + requested.height) + 2
            window = Window(col, row, right - col, bottom - row)
            if window.width * window.height > 1_000_000:
                raise ValueError("Unexpectedly large pilot window")
            values = src.read(1, window=window)
            profile = src.profile.copy()
            profile.update(driver="GTiff", width=int(window.width), height=int(window.height),
                           transform=src.window_transform(window), count=1,
                           compress="deflate", tiled=True, blockxsize=256, blockysize=256)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(destination, "w", **profile) as output:
                output.write(values, 1)
                output.update_tags(source_url=url, subset="native pixels, no resampling", units=source.get("units", "metres"))
            details = {"remote_headers": remote, "source_shape": [src.height, src.width],
                       "source_resolution_degrees": list(src.res), "source_nodata": src.nodata,
                       "source_window": {"column": col, "row": row, "width": int(window.width), "height": int(window.height)},
                       "acquisition_method": 'user_supplied_local_file' if local else 'http',
                       "acquisition_steps": ["Register and hash user-supplied file; no network request" if local else ("Full source cached after HTTP Range returned 200" if full_source else "HTTP byte-range read"), "pilot bbox plus two native pixels", "lossless native-grid subset; no resampling"]}
            if local:
                details.update(original_download_at=None, original_download_url=source.get('source_file_url'),
                               acquisition_date_note='acquired_at records local registration; original user download timestamp was not supplied',
                               checksum_origin='Locally computed SHA-256; no independent publisher checksum supplied')
    record_acquisition(dataset_id, source, destination, details)
    if full_source:
        from common import file_record, manifest_path, write_json
        manifest = read_json(manifest_path(dataset_id))
        manifest["raw_files"].append(file_record(full_source))
        write_json(manifest_path(dataset_id), manifest)


def document(dataset_id, source, pilot):
    destination = RAW / source["category"] / source["raw_name"]
    if verified_existing(dataset_id, destination):
        return
    print(f"Downloading source document: {dataset_id}", flush=True)
    with SESSION.get(source["url"], stream=True, timeout=60) as response:
        save_response(response, destination, pilot["max_download_bytes"])
    with destination.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            destination.unlink()
            raise ValueError("Source did not return a PDF")
    record_acquisition(dataset_id, source, destination, {"acquisition_steps": ["Unmodified source PDF download"]})


def osm_sources(pilot, only_category=None):
    forward = Transformer.from_crs(4326, pilot["metric_crs"], always_xy=True).transform
    inverse = Transformer.from_crs(pilot["metric_crs"], 4326, always_xy=True).transform
    extent = transform(inverse, transform(forward, box(*pilot["bbox_wgs84"])).buffer(pilot["road_buffer_m"]))
    west, south, east, north = extent.bounds
    bbox = f"({south:.8f},{west:.8f},{north:.8f},{east:.8f})"
    kinds = "|".join(pilot["speed_assumptions_kph"])
    roads = f'way["highway"~"^({kinds})$"]["area"!="yes"]["access"!~"^(private|no)$"]["motor_vehicle"!="no"]["motorcar"!="no"]{bbox};'
    queries = {
        "roads": roads,
        "hydrography": f'way{bbox}["waterway"];',
        "communities": f'node{bbox}["place"];',
        "safe_sites": ''.join(f'{element}{bbox}["amenity"~"^(school|college|university|hospital|community_centre|townhall|social_facility)$"];' for element in ('node', 'way')) + ''.join(f'{element}{bbox}["office"="government"];' for element in ('node', 'way')),
    }
    for category, body in queries.items():
        if only_category and category != only_category:
            continue
        # Only roads need context beyond the configured analysis region.
        feature_bbox = pilot['bbox_wgs84']
        feature_query_bbox = f'({feature_bbox[1]:.8f},{feature_bbox[0]:.8f},{feature_bbox[3]:.8f},{feature_bbox[2]:.8f})'
        if category != 'roads':
            body = body.replace(bbox, feature_query_bbox)
        dataset_id = f"osm_{category}"
        folder = category
        stamp = pilot["osm_snapshot_at"][:10].replace("-", "")
        destination = RAW / folder / f"osm_{category}_{stamp}.osm"
        if verified_existing(dataset_id, destination):
            continue
        if category == 'communities':
            query = f'[out:xml][timeout:60][date:"{pilot["osm_snapshot_at"]}"];{body}out meta;'
        else:
            query = f'[out:xml][timeout:180][date:"{pilot["osm_snapshot_at"]}"];({body});(._;>;);out meta;'
        query_path = CATALOG / "queries" / f"{dataset_id}.overpassql"
        query_path.parent.mkdir(parents=True, exist_ok=True)
        query_path.write_text(query + "\n")
        errors = []
        for endpoint in ("https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"):
            print(f"Downloading archived OSM {category} from {endpoint}", flush=True)
            try:
                with SESSION.get(endpoint, params={"data": query}, stream=True, timeout=210) as response:
                    save_response(response, destination, pilot["max_download_bytes"])
                root = ET.parse(destination).getroot()
                if root.tag != "osm" or root.find("remark") is not None or root.find("node") is None:
                    remark = root.findtext("remark") or "No nodes returned"
                    raise ValueError(f"Unsuccessful Overpass response: {remark}")
                source = {"name": f"OpenStreetMap archived {category}", "provider": "OpenStreetMap contributors / Overpass API",
                          "url": endpoint, "license": "ODbL-1.0", "license_url": "https://www.openstreetmap.org/copyright",
                          "original_crs": "EPSG:4326", "spatial_resolution": "Vector; mapping accuracy varies",
                          "temporal_coverage": pilot["osm_snapshot_at"], "classification": "volunteered_geographic_information",
                          "limitations": ["Historical map state, not verified field completeness", "Missing tags do not imply absence", "Not a disaster safety assessment"] +
                          (["Only mapped locality nodes; place polygons and relations omitted"] if category == "communities" else ["OSM relations omitted; way/node representation only"])}
                record_acquisition(dataset_id, source, destination, {"query": query, "request_bbox_wgs84": list(extent.bounds) if category == 'roads' else feature_bbox,
                                   "acquisition_steps": ["Archived Overpass snapshot", f"{pilot['road_buffer_m']}m metric road buffer" if category == 'roads' else 'Pilot bounding box', "complete referenced members and nodes", "metadata retained"] +
                                   (["Hydrography queries waterway ways only; natural=water and water multipolygon relations excluded to bound extraction"] if category == "hydrography" else [])})
                break
            except (requests.RequestException, ValueError, ET.ParseError) as error:
                errors.append(f"{endpoint}: {error}")
                destination.unlink(missing_ok=True)
        else:
            raise RuntimeError("; ".join(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["rasters", "documents", "osm"])
    parser.add_argument("--osm-category", choices=["roads", "hydrography", "communities", "safe_sites"])
    args = parser.parse_args()
    pilot = config()
    sources = read_json(CATALOG / "sources.json")
    for key, source in sources.items():
        if source["kind"] in ("raster_window", "local_raster") and args.only in (None, "rasters"):
            raster_window(key, source, pilot)
        elif source["kind"] == "document" and args.only in (None, "documents"):
            document(key, source, pilot)
    if args.only in (None, "osm"):
        osm_sources(pilot, args.osm_category)


if __name__ == "__main__":
    main()
