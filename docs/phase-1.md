# Phase 1 handoff

## Resume point

The interrupted workspace already had an independent Git root, ignore rules, the backend package and Pydantic domain schemas, the JSON replay fixture, four API endpoints, backend tests, frontend response types/client/formatters, the shared replay hook, and bindings throughout the existing console. The Leaflet component had been extracted. Dependencies and local environment configuration were installed. This work was retained.

At resumption the implementation still needed verification and finishing: TypeScript used `replaceAll` and `Array.at`, which did not match the existing ES2020 target; browser checks and run documentation were incomplete. No root README or Phase 1 handoff existed.

Completed after resumption: compatible string/array operations; direct primary-route recovery for absent backups; reset that also retries; error-state header labels; severity-aware map markers and unreviewed-site tones; restored original map marker icons; text-only API tooltips; a local map stacking context so Leaflet does not cover the sticky header when scrolling; a missing-backup regression test; connected browser verification; and these run/handoff documents. `Amazon/src/index.css` was not edited.

## Operational contract and assumptions

- One run: `demo-yamuna-2023`, revision `phase1-1`, timezone `Asia/Kolkata`. Everything operational in the fixture is synthetic, including gauge values and flood arrival times.
- Four fixed snapshots preserve the existing Evacuate/Prepare/Monitor/Clear controls. They select backend frames and update the entire shared scenario. There is no ticking wall clock, interpolation, forecasting model, or automatic polling.
- Default replay is 13 July 2023 at 01:21 IST. The gauge is 207.3 m, projected peak 208.1 m at 07:00. The 205.33 m danger threshold is a demo parameter, not a claim of validated station metadata.
- Severity has four values: `critical`, `high`, `warning`, `safe`. Default counts are one critical, one high, one warning, zero safe. Affected population totals 1,352. Monitor/Clear frames have all zones safe and zero currently affected people; route and road records remain available as future contingency information.
- In this demo a non-safe zone's entire listed population is counted as affected; safe zones contribute zero. This is an explicit fixture convention, not an exposure calculation.
- Route selections are previews. Selecting a backup changes all relevant UI context but does not reserve its destination or release the primary allocation. There is no simultaneous rerouting/capacity optimizer. Each individual backup can accommodate its zone within the baseline unreserved capacity.
- Replay data is applied only when summary/zones/plan agree on run, revision, frame, and replay timestamp. Requests are cancelled when selection changes; old responses cannot replace new selections. Authors must increment `revision` when editing the fixture. Response types are handwritten TypeScript mirrors of Pydantic schemas, not generated runtime validators.
- Route and flood geometry are illustrative polylines/polygons. Route distances were aligned with approximate lengths of those polylines, not real road-network paths; travel minutes remain demo vehicle estimates. Route labels such as “safe corridor” are illustrative names, not evidence of road safety. No geographic safety inference is made from the shaded polygon.

Default plans (all times IST on 13 July 2023):

| Zone | People | Severity | Primary / destination | Deadline / countdown | Backup / destination | Backup deadline / countdown |
| --- | ---: | --- | --- | --- | --- | --- |
| 07 | 643 | critical | 07-B / S4 | 01:55 / 34 min | 07-C / S2 | 02:15 / 54 min |
| 11 | 291 | high | 11-A / S2 | 02:15 / 54 min | 11-B / S1 | 02:30 / 69 min |
| 03 | 418 | warning | 03-A / S1 | 02:40 / 79 min | 03-B / S4 | 02:00 / 39 min |

The Zone 03 backup has an earlier deadline than its primary. Primary/backup is the authored preference, not a guarantee that backup always permits later departure. Each demo departure plus travel time falls before its corridor closure.

ITO's single closure timestamp is 01:55; Khadar's is 01:10. S4 corridor access ends at 02:25, S2 at 02:47, S1 at 03:15. ITO and the S4 corridor are different road records. Plan access windows are looked up from canonical road data; countdowns are computed from timestamps in the frontend.

| Site | Capacity | Primary assigned | Unreserved in default frame |
| --- | ---: | ---: | ---: |
| S4 | 1,500 | 643 | 857 |
| S2 | 1,000 | 291 | 709 |
| S1 | 1,000 | 418 | 582 |

Total assignable capacity is 3,500, with zero unassigned people under the authored primary assignments. H12's illustrative 900 places are excluded because the facility is unreviewed. H17 has unknown capacity and is excluded. No site is authority verified.

## Screen bindings and remaining mock behavior

| UI area | API source | Remaining limitation |
| --- | --- | --- |
| Header / replay controls | summary | Fixed synthetic frames, no live gauge or polling |
| Emergency Strip / Command Center | summary, zones, selected plan | Authored severity/action mapping; decorative exit-window and gauge graphics are illustrative |
| Priority zones | zones | Authored severity and primary deadlines, not a priority algorithm |
| Evacuation / Leaflet | selected plan plus summary sites, roads, polygon | Illustrative geometry, no road graph, isolation, routing, or flood computation |
| Advisory modal | shared zone and selected route | Local preview only; no message is sent or queued |
| Flood Intelligence | same summary/zones/plan | Synthetic projections; forecast-point controls only highlight a point and explicitly do not change replay time |
| Safe Sites | summary sites and derived capacity | Synthetic inventory; local filters work, review buttons only preview; no submission, verification or optimization |

All operational fixture values remain mocked even though they now come from the backend: gauge/peak/projections, populations, severity, arrival/departure/closure times, road depth, capacities, assignment choices, travel times, route coordinates, flood footprint and candidate elevation/area. Flood probability, clearance, flood surface and unreviewed road access show unknown/unassessed instead of invented probabilities. The OpenStreetMap basemap is a real external tile service; it does not validate any demo overlay.

## Verification

Automated checks after the final code changes:

- Backend: 21 tests covering health/summary/zones, all three zone plans, unknown identifiers, all four frames, population and capacity arithmetic, destination/route ownership, route endpoints, canonical closures, deadline/travel relationships, optional backup, timezone validation, local CORS, and edits propagating through API views.
- Frontend: three date/countdown tests, including 34/54/79 minutes, midnight rollover, expired deadlines, null standby deadlines, and explicit scenario timezone.
- TypeScript: `tsc --noEmit`.
- Production: `vite build`.
- Python environment: `pip check`.

The installed Starlette version emits one deprecation warning for its httpx-based TestClient. It does not fail the tests. Backend dependency ranges are declared in `pyproject.toml`; a full Python lockfile is not yet supplied. Frontend dependency versions remain governed by the existing unchanged pnpm lockfile.

Connected Chrome checks against the running frontend and FastAPI:

- Distinct primary and backup plans for Zones 07, 11, 03; selection persists across Command Center, Evacuation, Flood Intelligence and Safe Sites.
- Selected backup destination, deadline, route and countdown propagate into the advisory preview. “Simulate preview” confirms that nothing was sent.
- Default header: 207.3 m, 208.1 m peak, 1,352 affected, one critical zone, 01:21 replay; Zone 07 countdown 34 minutes.
- Monitor snapshot: 23:21 on the previous date, 204.8 m gauge, zero affected/critical zones, no departure required; closure countdown crosses midnight correctly.
- Missing-zone error via `?zone=99`; missing-backup error with direct primary recovery.
- Temporary fixture edit (650 people in Zone 07) appeared as 1,359 affected and 850 unreserved S4 places, without JSX edits or backend restart. Fixture was restored byte-for-byte immediately after this check.
- Temporarily paused the local API: loading appeared, the 10-second request timeout produced backend-unavailable, and retry recovered after the API resumed automatically.
- Served the completed production build on localhost:8444 against FastAPI: Command Center and Leaflet primary/backup views rendered, with no browser console errors or warnings. Screenshot: `artifacts/phase-1-command-center.jpg` (local, ignored by Git).

No test or UI action delivered messages or submitted an external review. Browser checks are manual tool-driven verification, not a newly installed browser-test framework.

## Exact file inventory

New source/configuration/documentation files introduced by Phase 1:

```text
.gitignore
README.md
docs/phase-1.md
backend/.env.example
backend/pyproject.toml
backend/app/__init__.py
backend/app/main.py
backend/app/api/__init__.py
backend/app/api/replay.py
backend/app/schemas/__init__.py
backend/app/schemas/replay.py
backend/app/services/__init__.py
backend/app/services/replay.py
backend/app/fixtures/__init__.py
backend/app/fixtures/demo-yamuna-2023.json
backend/tests/test_replay.py
Amazon/.env.example
Amazon/src/api/client.ts
Amazon/src/api/format.ts
Amazon/src/api/format.test.ts
Amazon/src/types/replay.ts
Amazon/src/hooks/useReplay.ts
Amazon/src/components/EvacuationMap.tsx
```

Existing frontend files modified during Phase 1:

```text
Amazon/src/App.tsx
Amazon/package.json
Amazon/.gitignore
Amazon/.figma/make/site.json
```

Local generated state, excluded from Git: `backend/.venv/`, Python/test caches and editable-install metadata, `Amazon/node_modules/`, `Amazon/dist/`, and `Amazon/.env.local`. `.git/` was initialized at the project root. Temporary verification backups live outside the repository under `/private/tmp/`.

The original `Amazon/src/index.css`, entry point, TypeScript configuration, Vite configuration, and pnpm lockfile were preserved. Title metadata is set through the existing Figma site configuration rather than rewriting its HTML/build setup.

## Git and scope

Both the project root and `Amazon/` resolve to `/Users/hrishitasingh/Documents/BharatBuilds`. The ancestor `/Users/hrishitasingh/.git` was not modified. This is a newly initialized repository with no commits, nothing staged, and all project source currently untracked. “Modified” in the inventory means changed relative to the supplied frontend, not `git diff` against a commit that does not exist. No project files were staged or committed into the ancestor repository.

Ignore rules cover local environment files, dependencies, frontend build output, virtual environments, caches, large raw/processed datasets, and generated artifacts. Example environment files remain trackable.

There are no remaining Phase 1 blockers. Real data provenance, pilot boundaries, flood/exposure computation, validated shelters/roads and transport assumptions remain future work. `data/`, `scripts/`, `models/` and `infra/` are reserved architecture, not Phase 2 implementations. Phase 1 ends here.
