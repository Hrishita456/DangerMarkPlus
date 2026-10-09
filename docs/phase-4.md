# Phase 4 — evacuation planning engine

Phase 4 consumes saved Phase 3 consequences and the Phase 2 graph/candidate facilities. It does not acquire data, regenerate flood consequences, change the Figma frontend, or implement Phase 5.

## Resume audit

Git resolved to `/Users/hrishitasingh/Documents/BharatBuilds`, with Phase 3 checkpoint `78d009e`. The working tree contained the Phase 4 router, schemas, service, all planning modules, configuration, tests, cached pilot output and `docs/phase-4-results.json`. The only modified tracked source was `backend/app/main.py`, registering the new router.

The interrupted commands had actually completed: 67 backend tests passed, and the real-pilot verifier confirmed independent recomputation, API responses, GeoJSON validity, road exclusions, backup independence and unchanged Phase 3 output checksums. Nothing needed rebuilding. After resuming, individual plans gained explicit provenance, the algorithm/cache version advanced to `phase4-1.0.1`, and the remaining regression checks and this handoff were completed. Working routing, assignment and timing algorithms were preserved.

## Algorithms and assumptions

### Safe-site eligibility

All 269 Phase 2 facilities retain their original IDs, names (including null names), types, source, verification status, capacity and capacity source. Eligible configured types include schools, colleges, universities, hospitals, community centres, town halls, government offices and social facilities. They remain **candidate destinations, not verified official shelters**.

A candidate must be in known scenario coverage, at least **100 m** from the supplied flood extent, and not within **10 m** of an excluded road edge. It must attach to its nearest baseline graph node within **150 m**, with a connector that stays in known coverage and does not intersect flood. That node must have permitted road edges. Reachability is then tested separately for each locality. Capacity is an assignment constraint, not a physical-safety classification.

Origin attachment reuses the Phase 3 baseline node where provided. The same 150 m limit and connector checks apply. Attachments are not moved to a different road after exclusions. Straight access connectors remain unsurveyed assumptions; a geometrically dry connector may still cross walls, private land or an unavailable entrance.

### Primary routing and travel times

The persisted directed MultiDiGraph is copied without mutation. The pilot excludes Phase 3 `closure_candidate`, `uncertain_structure`, `unknown` and `near_flood` edges. Parallel edges and directionality are preserved.

A deterministic heap-based **Dijkstra earliest-arrival search** minimizes estimated travel minutes from each origin to all candidate nodes. Positive edge costs use persisted metric lengths and speeds; invalid/missing speeds use configured road-class defaults. Speeds are multiplied by **0.5**, an explicit planning assumption, not observed evacuation traffic. Connector speed is **5 km/h**. Unknown classes default to 20 km/h before the multiplier. The complete class table is in `backend/config/phase4-pilot.json`.

Where explicit closure schedules exist, an edge is traversable only if cumulative travel through its **exit**, plus mobilization and safety buffers, finishes before closure. Earlier arrival dominates later arrival because costs are fixed and roads only close; no waiting/reopening model is implemented. Parallel alternatives remain available when one edge closes too early. Search results are cached per origin and exclusion set during planning.

Routes include geometry, metric distance, estimated travel time, directed edge IDs, cumulative edge-exit times, names, connector assumptions, mapped structures and bottlenecks. Bottlenecks include cut-links in the undirected simplified permitted graph and mapped bridges/tunnels/layers. This does not identify every directed-network bottleneck. Zero-edge connector-only trips are not reported as road evacuation routes.

### Destination ranking and assignment

For each reachable, physically eligible candidate, lower ranking score is better:

`travel_minutes + 0.1 × distance_km + 5 if unverified + 5 if capacity unknown + 10 × prior assigned localities`

Ties resolve by site ID. Assignment is deterministic greedy, ordered by descending pre-assignment risk score, then locality ID. It is not a global optimizer. The reuse penalty discourages concentrating provisional assignments at one unknown-capacity facility; it does not establish the facility's actual capacity.

**Demand stays null** unless explicitly configured. Overlapping Phase 3 population buffers are risk indicators, never passenger counts. With explicit demand and known capacity, the engine reserves people and subtracts from remaining capacity; insufficient sites are skipped. Unknown-capacity sites can receive provisional assignments, with capacity still null and no invented reserved headcount. If demand is unknown, known-capacity sites cannot be reserved: the result stays capacity-unknown unless an unknown-capacity candidate can be provisionally selected. Primary assignments share one ledger; a backup to the same site does not reserve capacity twice. Splitting one locality between sites is not implemented.

### Independent backup

For the selected destination, run the search again after removing **every primary network node-pair in both directions**, including parallel edges, and any edge sharing mapped OSM way IDs with primary bridges/tunnels/layered structures. If no route remains, return `backup_route: null`, `backup_status: unavailable` and a reason.

Available backups are independent under this graph-link definition. They still share origin/destination access connectors and may share junctions or correlated physical hazards. Parallel carriageways or separately mapped structures are not proven independently safe. A long detour is returned with its travel estimate rather than disguised as an equivalent route. The pilot's longest backup is approximately 24 minutes versus a 4-minute primary.

### Deadlines

The current pilot has **no closure-time schedule**, so every plan returns:

- `deadline_status: unavailable`
- `latest_departure: null`
- `latest_vehicle_departure: null`
- `urgency: unknown`

No arbitrary flood-arrival times or countdowns are invented. For explicitly supplied edge closure times, calculate for each threatened route edge:

`latest initiation = closure time − cumulative travel through edge exit − safety buffer − mobilization buffer`

Take the earliest constraint. `latest_departure` means latest **mobilization initiation**; `latest_vehicle_departure` excludes the mobilization subtraction. Pilot-configured buffers are 20 minutes mobilization and 10 minutes safety, but they do not create a deadline without closure evidence. Scenario-supplied times produce `scenario_estimate`; observed constraints still produce `observed_constraint_estimate` because travel times are assumed. Unscheduled roads and future destination safety remain unknown. Urgency uses the scenario timestamp, not the computer clock.

### Priority

Priority sums configured contributions:

- Severity: critical 50, high 35, warning 15, safe 0, unknown 20.
- Accessibility: isolated 35, at risk 25, degraded 10, accessible 0, unknown 15.
- Approximate buffer exposure: 2 points per 1,000 people, capped at 15.
- No feasible plan: 25; unknown capacity: 5.
- Supplied deadline elapsed: 30; within 60 minutes: 15. Unknown time adds no fabricated urgency.

Scores map to critical ≥75, high ≥50, moderate ≥20, otherwise low. Each plan returns the score, contributions and reasons. This is an illustrative prioritization policy, not an approved incident-command policy or ML. The pilot's 12 plans are all moderate.

## Results and uncertainty

The parent run remains `analysis-1616d67b7b28fb2442d9747f`: the hypothetical Phase 3 terrain scenario, not a validated July 2023 flood reconstruction. The new [machine-readable report](phase-4-results.json) gives the planning ID, full configuration, per-locality destinations, metrics, timing and validation evidence.

| Result | Count |
| --- | ---: |
| Affected/access-uncertain localities evaluated | 12 |
| Provisional primary routes | 12 |
| Independent network backup routes | 8 |
| Backup unavailable | 4 |
| No safe route / no safe site | 0 / 0 |
| Known capacity insufficient | 0 |
| Capacity unknown / sufficient / insufficient | 12 / 0 / 0 |
| Distinct selected candidate facilities | 12 |
| Candidate facilities / physically eligible candidates | 269 / 258 |
| Unknown evacuation demand | 12 |
| Null departure deadlines | 12 |

A feasible route is conditional on the scenario, road model and access assumptions; it does not establish that a candidate can shelter a locality. Approximate population remains 1 km information. There is no fleet, loading, congestion, shuttle, turn-restriction, building-access or shelter-operations model. Individual travel time is not total evacuation duration. The synthetic Phase 1 UI remains separate.

## APIs and reproducibility

- `GET /api/v1/runs/{run_id}/evacuation`: all plans, assignment ledger, configuration, provenance and counts.
- `GET /api/v1/runs/{run_id}/localities/{locality_id}/plan`: one affected locality, with provenance and nested candidate verification/capacity fields. The path accepts real IDs such as `osm/node/…`; URL encoding is supported.
- `GET /api/v1/runs/{run_id}/safe-sites`: all candidates as GeoJSON, suitability reasons and final assignment/capacity ledger.

All previous endpoints remain available. Unknown runs/locality plans return 404; invalid inputs return 409; missing optional GIS dependencies return 503. Valid no-route/no-capacity outcomes return normal plans, not server errors.

The first GET lazily builds local results; subsequent requests reuse a content-addressed cache under ignored `artifacts/evacuation/`. Its key includes the planning algorithm, canonical hashes of all four parent outputs and complete planning configuration. Files are atomically published, with a local lock preventing duplicate work in a process. Dataset snapshots are treated as immutable; restart after changing datasets. There is no database, worker service or external request. GIS calculations use the bundle's metric CRS (pilot EPSG:32643); output geometries use EPSG:4326 longitude/latitude.

From the repository root, using the existing combined GIS/API environment:

```bash
scripts/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Or compute/validate without starting a server:

```bash
PYTHONPATH=backend scripts/.venv/bin/python -m app.evacuation analysis-1616d67b7b28fb2442d9747f
PYTHONPATH=backend scripts/.venv/bin/python -m app.evacuation.verify
PYTHONPATH=backend scripts/.venv/bin/python -m pytest backend/tests -q
```

`EVACUATION_CONFIG` selects a trusted server-side JSON configuration. Explicit closure schedules map directed edge IDs to timezone-aware timestamps; demand overrides map real locality IDs to positive planning headcounts. Invalid IDs are rejected. The pilot supplies neither. No new dependencies or downloads were required in Phase 4; the existing Phase 3 lock/environment remains sufficient.

## Files

Created during Phase 4: `backend/app/evacuation/` (`routing`, `sites`, `assignment`, `deadlines`, `priority`, `planning`, verifier and CLI); `backend/app/api/evacuation.py`; `backend/app/services/evacuation.py`; `backend/app/schemas/evacuation.py`; `backend/config/phase4-pilot.json`; `backend/tests/test_evacuation.py`; `docs/phase-4-results.json`; this handoff.

Modified: `backend/app/main.py` for router registration; root README for the Phase 4 link. No changes to frontend, previous phase engines/tests, fixtures, datasets, manifests or previous validation reports. Phase 4 remains uncommitted; no Phase 5 work has started.

## Final validation

- **67 backend tests pass:** 21 Phase 1 replay, 26 Phase 3 consequence, 20 Phase 4 planning tests.
- Planning tests cover reachable/unreachable destinations, directionality and parallel edges, unsafe-edge exclusion, connector flood crossings, primary/backup geometry, shared-link/structure avoidance, no-backup, capacity reservation/exhaustion/zero/unknown demand, deterministic ranking/reuse, explicit closure timing and static null deadlines, priority contributions, API locality IDs containing slashes, cache invalidation, missing runs and input validation.
- **9 Phase 2 pipeline tests pass**, and **all 10 dataset checks pass**, including source/processed checksums.
- **3 frontend tests pass**; TypeScript check and production build pass.
- Real pilot verifier: independent planning output equals the persisted result; all aggregate/site/locality API views pass; excluded edges are absent; primary/backup road pairs are disjoint; route geometries are valid EPSG:4326; demands and deadlines remain null.
- Phase 3 output hashes remain identical. Git comparison confirms no changes to `Amazon/`, `data/`, `scripts/`, the Phase 3 engine/results, fixtures or previous tests. `git diff --check` passes.
- Existing Starlette/httpx and Affine deprecation warnings remain non-failing. No dependencies were changed to suppress them.

The resumed final run took about 20 seconds including first-load work, 0.7 seconds for a cached request, and 10.7 seconds for independent recomputation. These local timings were measured alongside regression jobs, not as a production load test. Full plans and reports are local, reproducible and uncommitted. Stop after Phase 4.
