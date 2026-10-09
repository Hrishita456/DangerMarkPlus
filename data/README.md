# Delhi/Yamuna pilot dataset bundle

Phase 2 supplies reproducible, separately catalogued geospatial inputs. The application still uses the Phase 1 **synthetic** `demo-yamuna-2023` fixture. This bundle does not calculate inundation, exposure, road closures, evacuation routes, shelter assignments, or deadlines.

## Fixed pilot

- Region ID: `delhi_yamuna`; version `1.0.0`.
- Wazirabad–Nizamuddin study corridor: **77.215–77.305°E, 28.590–28.715°N**.
- Bounding-box order: west, south, east, north. This rectangle is a project analysis boundary, not an administrative unit, catchment, or observed flood boundary.
- Analysis CRS: **EPSG:32643, WGS84 / UTM zone 43N**, metres.
- GeoJSON: **EPSG:4326**, coordinates `[longitude, latitude]`. Leaflet convenience arrays use `[latitude, longitude]`; these files do not use that order.
- Event window: 9–16 July 2023. OSM snapshot: **2023-07-13T12:30:00Z**, equivalent to 18:00 IST on 13 July.
- Road graph includes a **500 m metric buffer** for network context. Community/facility outputs remain inside the study rectangle.

The executable configuration is [catalog/pilot.json](catalog/pilot.json). The exact area, common grid bounds, counts, and checks are recorded in the [validation report](catalog/validation/report.md).

## Sources and interpretation

| Input | Source/provider | Source representation | Processed representation |
| --- | --- | --- | --- |
| Elevation | [Copernicus GLO-30 public COG](https://registry.opendata.aws/copernicus-dem/), Copernicus/ESA, hosted by Sinergise | N28 E077 tile, public 2021 release; 1 arc-second WGS84 pixels, EGM2008 metre heights; mostly 2011–2015 acquisitions | Clipped 30 m EPSG:32643 surface elevation, bilinear resampling |
| Population | [WorldPop Global2 R2025A country product](https://hub.worldpop.org/geodata/listing?id=136), University of Southampton; [DOI](https://doi.org/10.5258/SOTON/WP00840) | User-supplied `ind_pop_2023_CN_1km_R2025A_UA_v1.tif`: **2023, 1 km, R2025A, UA, v1**, 30 arc-seconds, **estimated persons per pixel** | Native 1 km crop retained; conservative count transfer to the existing 90 m EPSG:32643 grid **for alignment only**, with known-source coverage raster |
| Roads | [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), historical Overpass API | Drivable highway ways at the stated snapshot; one-way/access tags retained | Directed OSMnx/NetworkX GraphML plus nodes/edges GeoPackage, EPSG:32643 |
| Hydrography | Same historical OSM snapshot | Mapped `waterway` ways | Clipped river/stream/canal/drain/riverbank geometries, WGS84 GeoJSON; includes Yamuna |
| Communities | Same historical OSM snapshot | Named `place` nodes | Locality representative points; **no administrative polygons or assigned populations** |
| Candidate sites | Same historical OSM snapshot | Facility nodes/building ways: schools, colleges, universities, hospitals, community centres, town halls, social facilities, government offices | Representative points, source IDs, available access/operator tags, sampled DSM height; **unverified candidates**, capacity and capacity source `null` |
| Gauge/station | [CWC 2022 station catalogue](https://cwc.gov.in/sites/default/files/appraisal-report-2022-publication-no..pdf), PDF p.80 / printed p.73, Annex-II row 27 | Delhi Railway Bridge, rounded 28.66°N 77.25°E; warning 204.50 m, danger 205.33 m | Station GeoJSON; coordinate precision and datum caveat preserved |
| Historical peak | [CWC Delhi Floods 2023 case study](https://cwc.gov.in/sites/default/files/delhi-floods-2023-case-study.pdf), January 2025, PDF p.9 / printed p.4 | Reported **208.66 m at 18:00 IST, 13 July 2023** | Exactly one documented observation; **no invented hourly series** |
| Flood evidence: Shantivan | [NRSC/ISRO map](https://www.nrsc.gov.in/nrscnew/assets/pdf/maps_dms/dl_2023_12_07_0007_VAP.pdf) | Sentinel-2B image labelled 13 July 2023; map issued 14 July. URL filename contains an earlier date | Georeferenced cartographic evidence raster and map-coverage polygon, not a classified flood mask |
| Flood evidence: Shastri Park | [NRSC/ISRO map](https://www.nrsc.gov.in/nrscnew/assets/pdf/maps_dms/dl_2023_12_07_0008_VAP.pdf) | Inundation/standing-water map labelled 13 July; identifier contains 12 July; exact satellite acquisition timestamp unresolved | Same evidence representation; date conflict retained explicitly |

Exact source URLs, acquisition times, licences, temporal coverage, limitations, SHA-256 checksums, and preprocessing steps are in [catalog/manifests/](catalog/manifests/). [catalog/sources.json](catalog/sources.json) records the document/raster acquisition plan; [catalog/queries/](catalog/queries/) retains successful OSM query bodies.

The generated [file inventory](catalog/validation/inventory.md) lists every validated raw and processed path and its byte size. The prepared inventory includes 85 named locality points, 269 candidate facilities, 143 hydrography features, and a road graph with 32,239 nodes and 86,396 directed edges. These are OSM object counts, not verified counts of distinct real-world communities or shelters; overlapping/duplicate names may occur.

The [completion check log](catalog/validation/checks.json) records the latest population preparation, full validation, pipeline tests, Phase 1 tests, TypeScript check, and production build. Its status remains `waiting_for_population` or `running` until the batch finishes; a pending or failed batch is not Phase 2 completion.

Final validation: **10/10 dataset checks pass**, covering **25 unique raw/processed files** and **11 manifests**. The fractional source-cell population within the pilot is **2,842,043.3806058443**; the aligned raster totals **2,842,043.38060584**, an absolute conservation difference of **4.19 × 10⁻⁹ people**. This is the modelled population of the study rectangle under the uniform-cell clipping assumption, **not flood-exposed population**. There are 192 native source cells with positive-area overlap. All 21 artifacts completed before population was added retain their earlier checksums.

Copernicus attribution requirements apply; WorldPop is CC-BY-4.0; OSM is ODbL-1.0. The CWC reports are publicly accessible but an open redistribution licence has not been established. NRSC maps explicitly say **“For official use”**; public access does not establish permission to redistribute. Source PDFs and their rendered derivatives remain outside Git.

## Raster rules

Raster manifests record bounds, shape, CRS, resolution, dtype, nodata, and resampling. Metric grids share a 90 m snapped extent: three 30 m DEM pixels fit each 90 m population pixel. The common extent slightly exceeds the rectangle; masking controls which values belong to the pilot.

- **DEM:** native crop keeps its original pixels and source metadata. Bilinear projection is explicit; pixels with centres outside the study boundary become `-9999`. Copernicus is a **DSM**, including roofs/vegetation, with no river bathymetry. It is not bare-earth terrain.
- **Population:** the supplied source is **30 arc-seconds (0.0083333333°), approximately 1 km**, in EPSG:4326, float32, nodata `-99999`. The 20 × 16 native crop includes two pixels of padding and retains original pixel counts. Each valid source cell is projected to metric coordinates; its count is allocated by overlap area, assuming uniform population within that approximately 1 km cell. Boundary cells contribute only their in-boundary fraction. The existing 90 m grid is an **alignment artifact, not 90 m population information**. Output units remain persons per grid cell within the study boundary, never people/m². The manifest, raster tags and bundle index all record this limitation. No subpixel settlement distribution or fine-scale exposure is inferred.
- **Unknown population:** source nodata is not silently treated as zero. `-9999` means no known population contribution. The accompanying coverage fraction indicates how much of each grid cell's study intersection has valid source data. A partially known cell contains only its known contribution; this is not evidence of census completeness. Real source zeros stay zero.
- **Flood evidence:** both PDFs embed map projection **EPSG:32644** and geographic control points. The pipeline uses those source controls, then projects to the unchanged pilot CRS **EPSG:32643**. RGB imagery plus alpha is resampled with nearest neighbour onto the 30 m grid. That grid spacing is an output choice, **not the satellite's native resolution**. Labels/clouds remain. Alpha 0 means outside map coverage/study area; no flood/non-flood nodata semantics are implied.
- **Vertical datum:** CWC gauge datum has not been reconciled with Copernicus EGM2008. Subtracting the gauge elevation from this DSM is not a validated flood-depth calculation.

The `evidence_coverage.geojson` polygons describe the **map footprints**, not inundated land. Control-point residuals assess the internal affine fit, not independent positional accuracy. The two maps cover only part of the pilot.

## Reproduce locally

From `BharatBuilds/`, with Python 3.12:

```sh
python3.12 -m venv scripts/.venv
scripts/.venv/bin/python -m pip install -r scripts/requirements-lock.txt
scripts/.venv/bin/python -m pip check

# Requires network only when a verified source is missing.
scripts/.venv/bin/python scripts/download/acquire.py

# Offline, using cached inputs. Run preprocessing commands sequentially.
scripts/.venv/bin/python scripts/preprocessing/prepare.py
scripts/.venv/bin/python scripts/validation/validate_dataset.py
scripts/.venv/bin/python -m pytest scripts/tests -q
```

`requirements.txt` records intentional direct dependencies; `requirements-lock.txt` pins the tested full environment. This GIS environment is separate from `backend/.venv`; the API does not import it. Exact binary output checksums are tied to the recorded toolchain/platform; upgrades must regenerate and revalidate manifests.

For a partial workspace, avoid restarting successful acquisition:

```sh
scripts/.venv/bin/python scripts/download/acquire.py --only rasters
scripts/.venv/bin/python scripts/download/acquire.py --only documents
scripts/.venv/bin/python scripts/download/acquire.py --only osm --osm-category safe_sites
scripts/.venv/bin/python scripts/preprocessing/prepare.py --only rasters
scripts/.venv/bin/python scripts/preprocessing/prepare.py --only population
scripts/.venv/bin/python scripts/preprocessing/prepare.py --only roads
scripts/.venv/bin/python scripts/preprocessing/prepare.py --only features
scripts/.venv/bin/python scripts/preprocessing/prepare.py --only references
```

Acquisition verifies existing source checksums and refuses silently replacing changed or unmanifested files. Copernicus uses a small native window with byte ranges. **WorldPop is now local-only:** place the supplied 16,312,246-byte file at `data/raw/delhi_yamuna/population/ind_pop_2023_CN_1km_R2025A_UA_v1.tif`. Its expected SHA-256 is pinned in `sources.json`; a missing or changed file raises an error and never triggers a download. The original country file is preserved, hashed, and read only for the pilot window. Its exact original URL was recovered from the file's macOS browser-download metadata; the original download time and a publisher-provided checksum are unavailable. `acquired_at` records local registration time.

The abandoned 100 m/772 MB source is **not part of this bundle**. Its transfer and waiting batch were stopped when the user supplied and approved the 1 km replacement. No further population download is authorized or configured.

Do not start another acquisition while a `.part` file is being written. Failed transfers remain available for inspection. This downloader refuses to overwrite a partial file; it does not claim to support resuming against a server that ignores byte ranges. Overpass availability varies: saved extracts make preprocessing and validation independent of the live service. Error XML/HTML is not accepted as source data.

To finish population after the other layers already exist, use `--only population`; this preserves the completed DEM, boundary, graph, vectors, and reference artifacts. The final validator verifies all of them without regenerating them.

## Region-agnostic input contract

After **all** validation checks pass, [catalog/bundle.json](catalog/bundle.json) indexes these standard input roles:

`region_boundary`, `gauge`, `dem`, `population`, `road_graph`, `hydrography`, `communities`, `safe_site_candidates`, `historical_flood_evidence`.

Entries include representation labels, manifest IDs, paths, byte sizes, and checksums. The index records configuration/source-catalogue/toolchain hashes and explicit readiness flags. Validation failure removes a stale index, writes JSON/Markdown failure reports, exits nonzero, and preserves the datasets.

Processing is driven by the configuration rather than Delhi-specific analysis rules. For another region, create a separate catalogue containing `pilot.json` and `sources.json`, choose a distinct region ID, metric CRS, sources, gauge references and grid sizes, then set:

```sh
export PILOT_CONFIG="$PWD/data/catalog/another_region/pilot.json"
```

The catalogue and output directories follow this configuration. Source acquisition adapters currently handle WGS84 DEM/population rasters, archived OSM XML, and explicitly identified GeoPDF map viewports. A different source format needs an adapter, not Delhi-specific analysis branches. Never reuse `delhi_yamuna` for changed boundaries or different source editions.

## Limitations and next-phase boundaries

- OSM reflects mapping known at the historical snapshot, not verified July 2023 field completeness. Hydrography is waterway ways only; water-area multipolygons and `natural=water` features are omitted. Locality polygons and facility relations are also omitted.
- Graph edge lengths are measured in projected metres. Tagged speed limits are retained where parseable; otherwise explicit highway-class assumptions supply speed. `travel_time` is a free-flow estimate, not flood evacuation time. Small disconnected components are retained, not labelled flood isolation. Turn restrictions and conditional access are not evaluated.
- Candidate facility status does not establish public access, habitability, flood safety, availability, or shelter capacity. Capacity remains `null`; elevation alone does not verify safety. OSM access/operator tags, when present, are preserved for later review.
- Real locality IDs use OSM identities. `Zone 07`, `Zone 11`, and `Zone 03` remain exclusively synthetic UI labels.
- WorldPop is a retrospective demographic estimate, not event-day residents or evacuees. Its effective spatial detail remains approximately **1 km**, regardless of the aligned output grid. It cannot resolve individual settlements, roads or narrow flood edges. No population is assigned to individual communities in Phase 2. The `UA` filename variant is retained exactly; its suffix definition was not independently established from the consulted publisher pages.
- There is no classified historical flood mask, continuous observed gauge hydrograph, or resolved vertical datum transformation. These limitations must be addressed before quantitative flood validation or operational use.

## Git policy

`data/raw/**` and `data/processed/**` are ignored. Track only configuration, manifests, successful query bodies, small validation/index files, scripts, and documentation. Do not stage the country raster, graph, GeoPackages, PDFs, raster derivatives, virtual environments, or partial downloads. The independent repository root remains `BharatBuilds/`.
