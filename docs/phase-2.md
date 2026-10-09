# Phase 2 — reproducible pilot dataset foundation

The Phase 1 replay API and Figma/Leaflet frontend are unchanged. Phase 2 adds separately stored real geospatial inputs, provenance, preparation scripts, and validation. No Phase 3 analysis is implemented.

## Resume audit

**Latest resume, 9 October 2026:** all four archived OSM extracts, the Copernicus crop, four source PDFs, and twelve prepared artifacts were present. All **21 unique completed files** matched their manifest checksums. The 32,239-node / 86,396-edge graph, GeoPackage, 85 localities, 269 candidates, 143 hydrography features, gauge references and both georeferenced NRSC rasters were reused without reacquisition or rebuilding. Preprocessing, validation, tests and documentation code also survived.

The WorldPop transfer had failed with a network read timeout. Its still-running process had loaded an older downloader version whose `finally` block removed partial downloads; consequently no population source or partial file remained on disk. Workspace/temporary-file inspection and the process list confirmed this before recovery. New 16-byte range probes returned HTTP 200 and the full 771,534,851-byte length, so continuation was impossible. The approved source was restarted only after explaining this. The current downloader preserves partial files, refuses concurrent overwrites, prints progress, and uses a longer read timeout. A population-only preprocessing option avoids rebuilding completed layers.

The audit below records the earlier resume, before those prepared layers were completed.

**Final population source decision:** the user subsequently supplied `ind_pop_2023_CN_1km_R2025A_UA_v1.tif` and explicitly prohibited further WorldPop downloads. The obsolete transfer and waiting batch were stopped. This 16,312,246-byte, approximately 1 km raster replaces the planned 100 m source. Its original WorldPop `1km_ua/constrained/` URL was recovered from browser-download metadata. Registration and pilot-window processing are entirely local. The original file is unchanged; the existing DEM, graph, vectors and flood outputs are reused. Effective population information remains approximately 1 km; the 90 m output is conservative alignment only.

The independent Git root was verified as `/Users/hrishitasingh/Documents/BharatBuilds`, on `main`, with checkpoint `f3d85c6` (`Complete Phase 1 API-backed replay foundation`). At resume, Git showed only untracked `data/` and `scripts/`; no tracked Phase 1 files were modified. Raw/processed data were already excluded by the root `.gitignore`.

| State at interruption | Finding |
| --- | --- |
| Completed | Pilot/source configuration; isolated GIS environment and acquisition tooling; native Copernicus crop; July 2023 drivable-road OSM XML; two CWC PDFs; two NRSC PDFs; acquisition manifests for those six sources |
| Partial | Acquisition was incomplete: WorldPop and the combined historical OSM feature extract had not been obtained |
| Not yet started | Prepared standardized layers, persisted road graph, conservative population processing, validation suite/report, bundle index, dataset documentation |

The six existing source checksums were verified before reuse. Correct cached sources were preserved. The previous combined OSM request could not be reused because it had failed; successful smaller responses were retained. The large WorldPop download was started only after confirming it was missing and that the source ignored byte ranges.

## Work after resuming

- Completed historical OSM hydrography, locality, and facility acquisition using bounded GET queries. Saved query bodies and snapshot timestamps. No live/current OSM fallback is used.
- Prepared the study boundary, projected DSM, historical directed road graph/GIS layers, real locality points, candidate facilities, gauge reference, and NRSC evidence rasters.
- Implemented conservative population transfer with explicit nodata coverage and a source-versus-output count-conservation check.
- Read and visually inspected original NRSC PDFs and the derived map rasters. Used embedded controls in their declared UTM 44N map CRS, then transformed to pilot UTM 43N. Did not classify imagery or mislabel map footprints as flood extents.
- Added cache checks, partial-download protection, deterministic graph exports, configuration hashes, complete manifests, a standard bundle contract, offline tests, and machine-readable/Markdown validation.
- Updated the root README and added the detailed [dataset guide](../data/README.md). Kept all raw/processed datasets outside Git.

The definitive completion evidence is [validation/report.json](../data/catalog/validation/report.json). It reports failures while required inputs are absent; `bundle.json` is produced only when every check passes. No success is inferred from a download having merely started.

The latest end-of-phase command results are preserved separately in [validation/checks.json](../data/catalog/validation/checks.json), including exit codes and full test/build output. The obsolete download-waiting batch was stopped after the source change. Final checks validate the local population outputs and compare the 21 earlier artifacts against their saved checksums. They do not reacquire OSM or modify application files.

**Final result:** all 10 dataset checks pass; all 25 unique source/processed files match their checksums. Nine pipeline tests, 21 backend tests, three frontend tests, TypeScript, the production build, and both environment dependency checks pass. The 21 earlier artifacts are unchanged. The population source, native crop, aligned counts and coverage are the only new data artifacts in the final completion step.

Population output: `population/population_90m.tif` and `population/known_coverage_fraction_90m.tif`, EPSG:32643, 157 × 102 pixels. The native crop is `worldpop_2023_1km_native.tif`, EPSG:4326, 20 × 16 pixels at 30 arc-seconds with two pixels of padding. Of these, 192 cells overlap the study region. The fractionally clipped source total is **2,842,043.3806058443** people and the aligned sum is **2,842,043.38060584**; absolute numerical difference **4.19 × 10⁻⁹**. This whole-pilot model estimate is not an exposure calculation. The source file's SHA-256 is `c2859c04866c24759b66c3e327672832c78ad06772e436b8a1aceaf600b953bc`.

## Geography and exact inputs

The unchanged pilot is **77.215–77.305°E, 28.590–28.715°N**, approximately **121.94394 km²** in **EPSG:32643**. Web/GeoJSON output uses **EPSG:4326** longitude/latitude. The shared raster bounds are `[716310, 3164490, 725490, 3178620]` metres; the 30 m grid is 471 rows × 306 columns and the nested 90 m grid is 157 × 102.

The [dataset source table](../data/README.md#sources-and-interpretation) names each exact product, provider, temporal coverage, representation and source link. The [validated inventory](../data/catalog/validation/inventory.md) lists every raw and processed file. Eleven dataset manifests under `data/catalog/manifests/` cover:

`region`, `copernicus_dem`, `worldpop`, `osm_roads`, `osm_hydrography`, `osm_communities`, `osm_safe_sites`, `cwc_case_study`, `cwc_station_catalogue`, `nrsc_shantivan`, `nrsc_shastri_park`.

## Code and metadata

| Path | Purpose |
| --- | --- |
| `scripts/common.py` | Shared paths, atomic JSON, checksums, cache verification and manifest updates |
| `scripts/download/acquire.py` | Bounded raster acquisition, cached full-source fallback, source PDFs, archived OSM |
| `scripts/preprocessing/prepare.py` | Region boundary, metric rasters/graph, points, references, evidence raster preparation |
| `scripts/validation/validate_dataset.py` | Dataset integrity/representation checks, report, inventory and bundle index |
| `scripts/tests/test_pipeline.py` | Offline regression tests for count conservation, clipping, nodata, CRS, coordinates, IDs and download integrity |
| `scripts/requirements.txt`, `scripts/requirements-lock.txt` | Separate pinned GIS toolchain; no backend dependency changes |
| `data/catalog/pilot.json`, `sources.json` | Region and product configuration |
| `data/catalog/queries/` | Four successful historical Overpass query bodies |
| `data/catalog/manifests/` | Source and processed provenance, source/derived checksums, raster details, graph counts |
| `data/catalog/validation/` | Lightweight validation report and complete file inventory |
| `data/catalog/bundle.json` | Validated, representation-labelled standard input index |

The region-specific information is configuration and reference data. Generic preparation consumes configured bounds, CRS, resolution, source categories and timestamps. No Delhi-specific inundation, exposure, routing or priority rules are present.

## Verification and limitations

Nine offline pipeline tests cover conservation after grid changes, fractional edge-cell counts, source zeros versus nodata, all-unknown population, metric-grid rules, swapped coordinates, duplicate IDs, invalid JSON, truncated HTTP responses, compressed responses, existing partial download protection, and user-supplied raster registration with HTTP explicitly forbidden.

The dataset validator checks manifest completeness and hashes; the fixed boundary; DEM/population values and grids; population count conservation; graph geometry, CRS, speeds and time units; point identities and containment; unknown facility capacities; the single documented gauge observation; and flood-evidence alpha/control fit/representation. The canonical road GraphML and GeoPackage were rebuilt in separate Python processes and their SHA-256 values matched.

Application regression checks after resuming:

- Backend: **21 tests passed**, dependency check passed.
- Frontend: **3 tests passed**, TypeScript check passed, production build passed.
- GIS environment: dependency check passed; pipeline test results are above.
- Existing warnings: a backend Starlette/httpx deprecation and Affine 3 pending-deprecation messages in raster tooling; checks still pass.

Material limitations are recorded in each manifest and the validation report:

- CWC reference: **208.66 m at 18:00 IST on 13 July 2023**, with rounded catalogue coordinates. There is no measured hourly series and no established gauge-to-EGM2008 datum reconciliation.
- DSM is not bare-earth terrain or river bathymetry. Population is a retrospective model released in 2025, not event-day occupancy or evacuation demand. The approved replacement has approximately **1 km** information content. Redistribution to 90 m assumes uniform population inside native cells and must not be treated as fine-resolution evidence.
- Of 86,396 road edges, **85,001** use explicit class speed assumptions. There are **117** weak components before any flood analysis. No turn restrictions/conditional-access evaluation is included.
- The **85** locality points and **269** facility candidates are OSM elements, not verified administrative areas or unique operational shelters. All capacities are `null`; no safety/availability claim is made.
- Hydrography contains **143** mapped waterway features; water-area multipolygons and `natural=water` features are omitted. Locality polygons and facility relations are omitted as well.
- NRSC map footprints cover about **25.35%** of the pilot. Their RGB rasters are not binary flood masks. Clouds, labels and date ambiguity remain; control-fit residuals below 0.25 m do not establish positional accuracy. NRSC/CWC redistribution rights are not established.
- Phase 1 operational values, zones, routes, shelters and countdowns remain synthetic. No Phase 2 input has been silently wired into that fixture.

See [reproduction commands](../data/README.md#reproduce-locally) for acquisition/preprocessing/validation. Application run commands remain in the [root README](../README.md#run-locally). Stop at this dataset foundation; any flood or evacuation analysis requires a separately approved Phase 3.
