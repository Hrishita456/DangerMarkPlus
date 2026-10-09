# Phase 3 — deterministic flood consequences

Phase 3 adds a separate, region-configured analysis engine and API. The Phase 1 replay remains synthetic and unchanged; the Figma/Leaflet frontend is untouched. No Phase 4 allocation, evacuation routing, priority policy, exit deadlines or advisory generation is implemented.

## Starting checkpoint and input preservation

Started from clean independent Git root `/Users/hrishitasingh/Documents/BharatBuilds`, checkpoint `2d6f3e4` (Phase 2), following `f3d85c6` (Phase 1). Inspected the Phase 2 handoff, validated bundle/report, raster metadata, vector fields, and persisted graph. Reused all existing data without acquisition or preprocessing. The new local artifacts are ignored under `artifacts/consequences/`; no raw data, processed data, catalogues, manifests, existing validation outputs or frontend files are changed.

Pilot stays **77.215–77.305°E, 28.590–28.715°N**. Calculations use **EPSG:32643**, GeoJSON uses **EPSG:4326 longitude, latitude**. Region loading rejects geographic/feet analysis CRSs, missing/changed checksummed inputs, invalid vectors, invalid locality identities/locations, and empty/wrong-CRS graphs. The catalogue's original source references and limitations remain authoritative.

## Scenario and provenance

`backend/config/phase3-pilot.json` is the only pilot-specific analysis configuration. The engine accepts a standardized bundle, scenario metadata, timezone-aware replay timestamp, stage, flood specification and thresholds. `CONSEQUENCE_SCENARIO_CONFIG` selects another trusted server-side configuration; clients cannot submit filesystem paths. Restart after changing input datasets or bundle configuration because loaded region data are cached.

There is one stage: `single_assumed_surface`, in the historical peak context of **13 July 2023, 18:00 IST**. This timestamp does **not** establish that the calculated extent existed then. No intermediate stages are invented.

The shipped scenario uses an **illustrative uniform 205 m EGM2008 surface**, a round hypothetical level above typical river DSM cells. It is **not fitted to the CWC 208.66 m gauge peak**, whose datum remains unreconciled, and it is **not a validated historical reconstruction**. NRSC's four-band RGB/alpha images remain reference evidence, not classified masks or calibration targets. A scientifically stronger historical extent requires a defensible classified mask or hydraulic/datum work later; none is silently fabricated here.

Flood provenance distinguishes `terrain_approximation`, `scenario_assumption`, and `historical_evidence`. The trusted configuration can load a precomputed polygon or binary single-band raster. Raster input must have a CRS, 0/1 values and declared nodata; RGB and nonbinary inputs are rejected. Polygon input assumes complete extent coverage within the boundary; raster nodata remains unknown. Evidence provenance labels describe the supplied source, not independent validation by this engine.

## Exact algorithms

1. **Flood:** mark valid 30 m DSM cells at or below the assumed surface; retain four-neighbour-connected cells seeded within a configured 30 m buffer around mapped `waterway=river` features. Polygonize and clip to the pilot. Nodata blocks propagation. Valid-raster coverage is returned separately. This includes existing channel water; area is wet area, not newly flooded dry land. No flow, levee, drainage, bathymetry or hydraulic calculations occur.
2. **Population:** use the existing native WorldPop crop, not a second interpolation of the 90 m aligned product. Project each native pixel's corners into the metric CRS; multiply its people-per-pixel count by the fraction of projected area intersecting the flood polygon. Sum known contributions and report known-area coverage. Nodata never becomes zero. Uniform distribution within each native cell is an explicit assumption; approximately **1 km** information cannot resolve households or settlements. Results round to 100 people. An all-unknown nonempty query returns null; an empty intersection has zero exposure. Total flood exposure is computed once, never by summing locality buffers.
3. **Localities:** retain all 85 real OSM representative points. Report point inundation, distance to flood, exposure within a configured **500 m buffer clipped to the pilot**, flood-data coverage, road effects, snap distance, accessibility, severity and reasons. Buffers overlap and are not administrative boundaries or population assignments. Their estimates are not additive.
4. **Roads:** inspect every directed graph edge. An at-grade intersection of at least **1 m** is a precautionary `closure_candidate`, not an observed closure. Intersections on a bridge, tunnel or nonzero layer become `uncertain_structure`; no deck elevation is invented. Roads within **30 m** are `near_flood` and remain enabled. Edges leaving known flood coverage are `unknown`, unless a known intersection already supplies a stronger status. Preserve name, class, structural tags, metric length and intersection length. Counts are **directed edges**, not unique physical roads. The road GeoJSON contains all non-`unaffected` edges, including coverage uncertainty.
5. **Connectivity:** gateways are nodes in the largest baseline weak component, inside the **200 m inner boundary ring**, on known terrain and more than **200 m from flood**. They represent access to the model boundary, not verified safe destinations. Reverse directed searches identify nodes with an outgoing path to any gateway. The optimistic graph removes closure candidates; the cautious graph additionally removes uncertain structures and unknown-coverage edges. Localities snap once to the nearest baseline node within **300 m**, with no post-closure resnapping. The off-network connector is assumed, not surveyed. Baseline disconnection, no gateways or excessive snap distance yields `unknown`; loss of optimistic reachability yields `isolated`; optimistic-only access yields `at_risk_of_isolation`; retained cautious access with nearby scenario-affected roads yields `degraded_access`; otherwise `accessible`. Merely being near an outside-coverage road does not count as flood degradation.
6. **Severity:** `critical` for loss of baseline access; `high` for flooded point or access dependent on uncertain roads; `unknown` for insufficient point/baseline access information; `warning` for degraded access, flood within **200 m**, or a positive rounded population estimate in the locality buffer; otherwise `safe`. “Safe” means no configured trigger in this scenario, not verified physical safety. Numerical thresholds live in configuration. Rule ordering and reason strings are explicit, not ML.

Population coverage measures coverage of the calculated flood query, not confidence in the flood model. Flood-known coverage is separately reported. Roads outside the study rectangle remain uncertain. Baseline OSM has disconnected components and lacks turn-restriction/conditional-access validation.

## API and caching

- `POST /api/v1/runs/analyze` with `{"scenario_id":"yamuna-2023-illustrative-terrain"}`; `{}` selects that configured default.
- `GET /api/v1/runs/{run_id}/summary`
- `GET /api/v1/runs/{run_id}/localities`
- `GET /api/v1/runs/{run_id}/road-impacts`
- `GET /api/v1/runs/{run_id}/flood`

The existing `demo-yamuna-2023` summary/zones/plans retain their contracts. The summary route dispatches `analysis-*` run IDs to computed results. CORS now permits JSON POSTs from the same configured local origins. HTTP 404 means unknown scenario/run, 409 means invalid/missing analysis input, 422 means invalid request, and 503 means missing optional GIS dependencies. The unchanged health response remains the Phase 1 compatibility response; it does not assert GIS readiness.

Pydantic validates requests, scenario configuration, summaries and GeoJSON envelopes. GeoJSON carries source/reason properties; the summary provides the full scenario, algorithm version, bundle hash, replay context, assumptions and limitations.

The first analysis runs synchronously in FastAPI's thread pool; other read requests can continue. A local lock prevents duplicate concurrent analysis in a process. Two region loads are cached in memory. Run IDs hash algorithm version, bundle hash, complete scenario and any precomputed extent checksum. Four JSON outputs are atomically published in an ignored local directory. Repeated calls reuse results. There is no queue, worker service, database or external request. Restart after dataset changes; change the algorithm version when changing computation. Disk output retention is manual for this single-pilot phase.

## Run and reproduce

From the repository root, the existing GIS environment now also has the small API/test dependencies; no datasets were downloaded:

```bash
PYTHONPATH=backend scripts/.venv/bin/python -m app.geospatial
scripts/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Analyze over HTTP:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/runs/analyze \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id":"yamuna-2023-illustrative-terrain"}'
```

Use the returned `run_id` for the four read endpoints. API docs are at `http://127.0.0.1:8000/docs`. The UI continues to request the original demo run. Existing frontend command: `cd Amazon && corepack pnpm@10.34.3 dev`.

For a fresh combined environment, install `backend/requirements-phase3-lock.txt` and the editable backend (`python -m pip install --no-deps -e backend`). The lock records the tested combined GIS/API environment, including existing preprocessing dependencies. Alternatively the backend declares a `geospatial` extra: `python -m pip install -e 'backend[geospatial,test]'`. The original `backend/.venv` still supports Phase 1 without GIS; it returns a controlled 503 if analysis is attempted there.

Checks:

```bash
PYTHONPATH=backend scripts/.venv/bin/python -m pytest backend/tests -q
PYTHONPATH=backend scripts/.venv/bin/python -m app.geospatial.verify
scripts/.venv/bin/python -m pytest scripts/tests -q
scripts/.venv/bin/python scripts/validation/validate_dataset.py
git diff --exit-code -- data scripts Amazon
```

The optional real-bundle verifier checks cached requests, all read endpoints, and an independent full recomputation against serialized saved output, then writes `docs/phase-3-results.json`. Unit tests use tiny synthetic fixtures and require no pilot files or internet. The Phase 2 validator deterministically rewrites its existing reports; Git comparison confirms their contents remain unchanged.

## Files and checks

New: `backend/app/geospatial/{__init__,__main__,spatial,flood,exposure,roads,connectivity,consequences,verify}.py`; `backend/app/{api,schemas,services}/consequences.py`; `backend/config/phase3-pilot.json`; `backend/tests/test_consequences.py`; `backend/requirements-phase3-lock.txt`; this document and `docs/phase-3-results.json`.

Modified: `backend/app/api/replay.py` (computed summary dispatch), `backend/app/main.py` (router/CORS/description), `backend/pyproject.toml` (optional GIS dependencies), root README (handoff link). No frontend, fixture, Phase 2 script or dataset changes. No commit created.

Final checks and exact pilot metrics are recorded below and in the machine-readable results. Existing Starlette/httpx and Affine pending-deprecation warnings are non-failing. They were not “fixed” by unrelated dependency upgrades.

## Validated pilot result

Run: `analysis-1616d67b7b28fb2442d9747f`, algorithm `phase3-1.0.2`. Full scenario, provenance, output checksums and locality detail: [phase-3-results.json](phase-3-results.json). The independently recomputed JSON exactly matches all four cached outputs.

| Metric | Result |
| --- | --- |
| Scenario wet area (includes river channel) | 11.395 km² |
| Estimated population in calculated wet area | Approximately 72,900 people |
| Population coverage of that wet area | 100% |
| Known flood-raster coverage of pilot | 99.8597% |
| Real locality points directly wet | 0 of 85 |
| Locality buffers with positive rounded exposure | 8; not additive |
| Accessibility | 73 accessible, 11 degraded, 1 unknown |
| Newly isolated / at risk of isolation | 0 / 0 in this scenario |
| Severity | 73 safe within scenario, 11 warning, 1 unknown; no high/critical |
| Directed road edges | 86,396 |
| Closure candidates | 476 |
| Uncertain structures intersecting flood | 30 |
| Near flood | 171 |
| Unknown road coverage | 14,978 |
| Unaffected | 70,741 |
| Boundary gateway nodes | 1,777 |

The unknown locality is **Tibetan Colony**. Its unknown access is not asserted to be flood-caused isolation. Zero directly wet representative points does not imply that their surrounding communities are unexposed. The whole-pilot population cross-check rounds to 2,842,000, consistent with Phase 2's unrounded 2,842,043.38.

| Locality | Severity | Accessibility | Approximate buffer population exposure |
| --- | --- | --- | --- |
| Pandav Nagar | warning | degraded_access | 0 |
| Chandrawal | warning | degraded_access | 0 |
| Majnu Ka Tila | warning | degraded_access | 1400 |
| Tibetan Colony | unknown | unknown | 3100 |
| Mayur Vihar I Pocket - 4 | warning | degraded_access | 1100 |
| Patparganj | warning | degraded_access | 0 |
| Janta Garden | warning | degraded_access | 2000 |
| Samaspur | warning | degraded_access | 1900 |
| Aruna Nagar | warning | degraded_access | 1300 |
| New Chandrawal | warning | degraded_access | 1000 |
| Safeda Basti | warning | degraded_access | 1500 |
| Kashmere Gate | warning | degraded_access | 0 |

The first computation took **29.44 seconds**, the repeated analysis request **0.007 seconds**. Read endpoints measured 0.004–0.204 seconds locally. These are single-machine observations, not a load-test guarantee. The non-unaffected road GeoJSON is approximately 8 MB; frontend filtering/pagination can be considered during the later integration phase.

Final checks: **47 backend tests pass** (21 replay + 26 consequence tests); **9 Phase 2 pipeline tests pass**; **all 10 dataset checks pass**, including 25 source/processed file checksums; **3 frontend tests**, TypeScript and production build pass. Both Python environments pass `pip check`. The original backend-only environment also passes its 21 replay tests, with the GIS test module skipped as expected without the optional extra. Final Git comparison confirms `data/`, `scripts/` and `Amazon/` remain unchanged.

Git remains on the independent BharatBuilds repository at Phase 2 checkpoint `2d6f3e4`, with Phase 3 source/configuration/documentation changes uncommitted. Phase 3 stops here; no Phase 4 work has begun.
