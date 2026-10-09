# Phase 5 — frontend integration and validation

## Status and resume audit

Integration and automated regression checks pass. **The full browser journey and fresh console review remain pending manual confirmation. Phase 5 is not yet signed off.** No Phase 6 work has started.

The repository root is `/Users/hrishitasingh/Documents/BharatBuilds`; the starting checkpoint is Phase 4 (`8f751ba`). Before editing, the working tree already contained the analysis types, typed API client, shared analysis hook, `AnalysisMap.tsx`, `AnalysisPages.tsx`, App mode selector/header integration, replay enable/disable guard, small styling additions and ten analysis API/state-helper tests. These survived the interruption and were preserved. The latest resume reran all checks and added this handoff plus current README guidance. No backend, pipeline, dataset, fixture or earlier result-report changes were necessary.

## Integrated screens and data

The selector offers `demo-yamuna-2023` and the saved pilot `analysis-1616d67b7b28fb2442d9747f`. This is a fixed selector, not a run-discovery service. Analysis is a **hypothetical 205 m EGM2008 terrain surface**, not a reconstruction calibrated to the 208.66 m gauge peak. The header uses backend population (approximately 72,900), extent, affected access and scenario timestamp.

| Screen | Backend content |
| --- | --- |
| Command Center | Summary, affected localities, selected plan, priority reasons, candidate destination, capacity, route and deadline status |
| Evacuation | Individual locality plan, primary/backup geometries and metrics, unavailable reasons, uncertainty and provenance |
| Flood Intelligence | Flood extent, population estimate, road impact categories, locality accessibility and model limitations |
| Safe Sites | Candidate facilities, eligibility/reasons, verification, assignment ledger and capacity fields |
| Advisory preview | Selected locality/destination/route and honest uncertainty; simulated issuance only, nothing sent |

Leaflet renders supplied EPSG:4326 GeoJSON: flood, affected locality points, closure-candidate roads, both available routes and the selected candidate destination. No frontend flood or route computation is performed. Map camera defaults are presentation settings, not synthetic operational geometry. Basemap tile failures and empty flood collections have explicit notices.

The hook is mounted above page navigation. Locality and route selections persist between screens; changing locality resets to primary. Demo and analysis hooks maintain separate context. Loading, abort, error/retry and response-consistency checks prevent demo fallback or displaying a mismatched plan. Browser verification of cross-screen persistence is still pending; helper tests are not a substitute for a mounted React interaction test.

## APIs consumed

All paths below are prefixed `/api/v1/runs/{run_id}`:

- `GET /summary`
- `GET /localities`
- `GET /road-impacts`
- `GET /flood`
- `GET /evacuation`
- `GET /safe-sites`
- `GET /localities/{locality_id}/plan` (OSM IDs are URL-encoded)

The first six load together; individual selection loads and checks its plan against the aggregate. Planning endpoints allow 60 seconds for a cold local cache; other reads allow 10 seconds. The frontend checks run/bundle/time identity, locality properties, the site ledger and complete individual-plan equality. It does not create analysis runs. Demo still consumes its original summary/zones/zone-plan APIs and replay snapshots.

## Automated validation on resume

| Check | Result |
| --- | --- |
| Backend Phases 1, 3, 4 | 67 tests passed |
| Phase 2 pipeline | 9 tests passed |
| Dataset validation | 10 checks passed, no failed checks |
| Frontend | 13 tests passed: 3 existing formatting tests plus 10 analysis tests |
| TypeScript | Passed (`tsc --noEmit`) |
| Production build | Passed (Vite 8.0.5) |
| Earlier backend/data/scripts/report changes | None |

Analysis unit tests cover six-resource loading, individual-plan consistency, demo separation, changed capacity rejection, site ledger consistency, locality selection resetting the route, primary/backup lookup, null capacity/deadline presentation, API failure and empty collections. They exercise API/state helpers, not mounted components or an automated end-to-end browser. Loading indicators, cross-screen persistence, modal focus and visual geometry therefore require the browser checklist below.

Non-failing existing warnings remain: Starlette/httpx test-client deprecation and Affine multiplication deprecations in raster tests. No dependency changes were made to suppress them. Frontend type/build checks emitted no errors.

Reproduce from the root using the existing environments:

```sh
PYTHONPATH=backend scripts/.venv/bin/python -m pytest backend/tests -q
scripts/.venv/bin/python -m pytest scripts/tests -q
scripts/.venv/bin/python scripts/validation/validate_dataset.py
cd Amazon
corepack pnpm@10.34.3 test
corepack pnpm@10.34.3 run typecheck
corepack pnpm@10.34.3 run build
```

## Browser evidence and remaining checklist

Native Chrome inspection confirmed the initial demo, switching to analysis, the approximately 72,900 population header, Tibetan Colony's real candidate plan and Evacuation screen with unknown capacity/deadline and unavailable backup. Native browser controls became unreliable for offscreen selectors. To avoid spending further credits on that control problem, the user was asked to finish the following manual journey at `http://localhost:8443` (backend `http://localhost:8000`). **No full-journey or clean-console claim has been made.**

1. Select **ANALYSIS RUN** and **Janta Garden**. Inspect Command Center, then Evacuation.
2. Confirm destination **Government Primary School for the Deaf**; capacity and deadline remain unknown/unavailable. Primary is approximately 0.24 km / 1.9 min.
3. Switch to backup: approximately **0.56 km / 3.7 min**. Confirm the separate route highlight and inspect flood, locality, closure-road and destination overlays (zoom out where needed).
4. Visit Safe Sites, Flood Intelligence and Command Center; verify Janta Garden and backup selection persist, and the destination/capacity/deadline agree.
5. Select **Tibetan Colony**: primary should be selected after locality change. Its destination is **TCV DAY School Samyeling**; primary approximately 0.13 km / 1.2 min. Selecting backup must show unavailable, without presenting the primary as a backup.
6. Preview/simulate advisory. Confirm its locality/route/destination and unknown capacity/deadline; simulation must say nothing was sent.
7. Return to **DEMO REPLAY**; confirm independent synthetic zone/snapshot controls still work and are labeled demo. Return to analysis and confirm no synthetic Zone 07/643-person/01:55 deadline values leak into it.
8. With Chrome DevTools Console cleared, repeat navigation and report any new error/warning. Basemap network failures should produce the explicit tile notice. Test API failure by stopping the backend and reloading; expect retry/error, no demo fallback, then restart and retry.

Pending manual result: not supplied at handoff creation. Record the actual outcome before declaring Phase 5 complete.

## Remaining limitations and intentionally simulated behavior

- Candidate sites remain unverified. All 12 current plans have unknown capacity, unknown evacuation headcount and null deadlines. Population within overlapping locality buffers is an exposure indicator, never passenger demand.
- Current backend outputs contain 12 primary routes, 8 independent backups and 4 unavailable backups. Feasibility is conditional on the existing Phase 3/4 assumptions; the frontend does not improve underlying certainty.
- Population effective resolution is 1 km. Flood extent and road exclusions are model scenarios, not live observations. Static analysis has no temporal replay or invented countdown.
- Original Phase 1 zones, populations, shelter capacities, route geometries and countdown snapshots remain intentionally synthetic and confined to demo mode. See `phase-1.md` for the original inventory.
- Advisory issuance is local simulation; there is no messaging or delivery claim.
- Leaflet basemap uses external OpenStreetMap tiles; data overlays come from the local backend. Only closure-candidate roads and planned localities are drawn to limit clutter. Route selection refits/recreates the map; map pan/zoom is not preserved across that change.
- Existing desktop layout/minimum width is preserved; this phase does not add responsive/mobile redesign. The run/locality/route context is in memory, not persisted across a full page reload.
- Saved analysis artifacts and datasets are intentionally ignored by Git. A fresh checkout needs the documented earlier-phase preparation; a missing local run displays an error rather than synthesizing replacements.

## File inventory and Git

Existing Phase 5 modifications preserved: `Amazon/package.json`, `Amazon/src/App.tsx`, `Amazon/src/api/client.ts`, `Amazon/src/hooks/useReplay.ts`, `Amazon/src/index.css`.

Existing Phase 5 new files preserved: `Amazon/src/api/analysis.ts`, `Amazon/src/api/analysis.test.ts`, `Amazon/src/types/analysis.ts`, `Amazon/src/hooks/useAnalysis.ts`, `Amazon/src/components/AnalysisMap.tsx`, `Amazon/src/components/AnalysisPages.tsx`.

Latest resume documentation: new `docs/phase-5.md`, updated root `README.md`. All Phase 5 changes remain uncommitted. No unrelated ancestor repository, backend/model change, acquisition, deployment or Phase 6 work is involved.
