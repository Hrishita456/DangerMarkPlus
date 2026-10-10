# DANGER MARK+ — Flood Consequence & Evacuation Intelligence

The existing `Amazon/` React console reads FastAPI through a typed API client. The scenario selector separates the synthetic Phase 1 demo replay from the saved Phase 3/4 analysis. **Neither mode is validated operational evacuation guidance or a verified July 2023 flood reconstruction.**

The Figma frontend remains in `Amazon/`. Its branding, desktop layout, and Leaflet map stack are preserved. Consequences and provisional routing use the local geospatial datasets and explicit model assumptions. Messaging, databases and authentication are not implemented. The hackathon deployment uses AWS serverless hosting.

Phase 2 adds a separate [Delhi/Yamuna dataset pipeline](data/README.md): catalogued sources, offline geospatial preprocessing, and validation. The real datasets are not connected to the synthetic replay. See the [Phase 2 handoff](docs/phase-2.md) for the resumed implementation, source inventory, checks, and limitations.

Phase 3 adds a separate [deterministic flood-consequences engine](docs/phase-3.md), with population overlap, road impacts, locality accessibility and run-oriented APIs. Its pilot uses an explicitly hypothetical terrain surface, not a validated historical flood reconstruction. The existing frontend and demo replay remain unchanged. See [computed results](docs/phase-3-results.json) for assumptions, metrics and reproducibility checks.

Phase 4 adds an [evacuation planning engine](docs/phase-4.md) over saved Phase 3 results. It provides provisional destination assignments, primary/independent backup routes and explicit capacity/timing uncertainty. See [pilot planning results](docs/phase-4-results.json).

Phase 5 integrates those saved outputs into Command Center, Evacuation, Flood Intelligence, Safe Sites and a simulated advisory preview. See the [Phase 5 handoff and browser checklist](docs/phase-5.md) for validation status, API coverage and limitations. The original demo remains independently selectable.

Phase 6 is complete for the hackathon deployment (browser validated 11 October 2026): [public frontend](https://dq0ijb66nf6yb.cloudfront.net), [backend health](https://4pc12p8rt1.execute-api.ap-southeast-2.amazonaws.com/api/v1/health). The frontend uses private S3 + CloudFront; the backend uses API Gateway HTTP API + Lambda, with its image in ECR. Compact pilot inputs/results are bundled in the image; no runtime-data bucket is needed. See [AWS architecture, resource IDs and validation](docs/aws-architecture.md), [environment configuration](infra/.env.example), and [three-minute demo](docs/demo-flow.md).

**Deployment limitations:** gzip is required for the large road-impact endpoint. A first cold start returned HTTP 503 after approximately 32.5 seconds; warm endpoint checks passed. Before a demo, open the health endpoint, wait for `status: ok`, then load the frontend. Concurrent scale-out may still encounter cold starts. This is a hackathon demonstration, not production-certified disaster infrastructure.

## Run locally

For the existing complete workspace, start the backend with the already installed combined GIS/API environment (no reinstallation or dataset acquisition needed):

```sh
scripts/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The following minimal backend setup supports the demo alone; analysis additionally needs the Phase 2/3 environment, datasets and saved outputs described in their handoffs.

Tested with Python 3.12.3, Node 22.22.1 and pnpm 10.34.3. The backend supports Python 3.11+; use Node 22.18+ for the frontend's TypeScript test command. Run the two services in separate terminals.

Backend, starting from this repository root:

```sh
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For an already installed workspace, only the last command is needed. API documentation: <http://localhost:8000/docs>.

Frontend, starting from this repository root:

```sh
cd Amazon
corepack pnpm@10.34.3 install --frozen-lockfile
test -f .env.local || cp .env.example .env.local
corepack pnpm@10.34.3 run dev --host 127.0.0.1
```

Open <http://localhost:8443>. `Amazon/.env.local` should contain `VITE_API_BASE_URL=http://localhost:8000`. This variable is an origin, without `/api/v1`. Vite reads it at startup/build time; restart Vite after changing it. If omitted, requests use the frontend's own origin, which requires an `/api/v1` reverse proxy (none is configured in Phase 1). Do not put secrets in Vite variables.

`backend/.env.example` documents optional `CORS_ORIGINS`; export it in the backend shell if overriding the local defaults. The backend does not automatically load `.env`. Defaults allow localhost and 127.0.0.1 on ports 8443 and 8444. Leaflet's existing OpenStreetMap basemap needs internet access; demo geometry and API data are local.

## Checks

```sh
# From BharatBuilds/
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

```sh
# From BharatBuilds/
cd Amazon
corepack pnpm@10.34.3 run typecheck
corepack pnpm@10.34.3 test
corepack pnpm@10.34.3 run build
# Optional local check of the built frontend, with the backend running:
corepack pnpm@10.34.3 run preview --host 127.0.0.1 --port 8444
```

## API

All frontend-consumed endpoints are read-only. JSON numbers remain numbers; dates are ISO 8601 with timezone offsets. Presentation formatting lives in the frontend. Analysis endpoints are listed in the [Phase 5 handoff](docs/phase-5.md); the table below describes the separate demo.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Process health and demo mode |
| GET | `/api/v1/runs/demo-yamuna-2023/summary` | Shared replay context, gauge, peak, totals, capacity, roads and illustrative map data |
| GET | `/api/v1/runs/demo-yamuna-2023/zones` | Zone severities, population and primary assignments |
| GET | `/api/v1/runs/demo-yamuna-2023/zones/{zone_id}/plan` | Requested zone's primary and optional backup plan |

Supported zone IDs: `07`, `11`, `03`. Run endpoints accept `?frame=evacuate` (default), `prepare`, `monitor`, or `clear`. These are fixed demo snapshots, not live simulation. Unknown runs, frames and zones return structured 404 errors. `/health` checks that the service is up, not the validity of an edited fixture.

## Repository

```text
BharatBuilds/                 # Independent Git root
├── Amazon/                  # Existing React / Vite / TypeScript / Tailwind / Leaflet
│   └── src/
│       ├── api/             # Typed fetch client and date/countdown formatting
│       ├── types/           # API response interfaces
│       ├── hooks/           # One shared run/frame/zone/route state
│       └── components/      # Leaflet component, driven by API data
├── backend/
│   ├── app/
│   │   ├── api/             # HTTP boundary
│   │   ├── schemas/         # Pydantic response/fixture validation
│   │   ├── services/        # Deterministic views and derived totals
│   │   └── fixtures/        # Small, version-controlled demo JSON
│   └── tests/
├── data/
│   ├── catalog/             # Config, manifests, queries, bundle index and validation
│   ├── raw/                 # Cached original inputs (ignored by Git)
│   └── processed/           # Prepared geospatial bundle (ignored by Git)
├── scripts/
│   ├── download/            # Bounded, cached acquisition
│   ├── preprocessing/       # Offline preparation; isolated GIS environment
│   ├── validation/          # Integrity/representation checks and bundle index
│   └── tests/               # Offline pipeline regression tests
└── docs/
    ├── phase-1.md           # Replay invariants, tests and mock inventory
    └── phase-2.md           # Dataset handoff and known limitations
```

`models/` remains reserved; `infra/` contains deployment wrappers, configuration, resource IDs and smoke checks. Large datasets and generated output stay out of Git; only small manifests and validation metadata are tracked. Geospatial preprocessing lives in `scripts/` and does not add dependencies to the replay backend. No database, distributed processing or ML model is added.

## Edit the demo

The single source is [`backend/app/fixtures/demo-yamuna-2023.json`](backend/app/fixtures/demo-yamuna-2023.json). Change its numeric values/timestamps and increment `revision`, then refresh the browser or change snapshots. Each API request re-reads and validates the file; no JSX edit or backend restart is needed. Save the complete file before refreshing. The frontend rejects mixed revisions and offers retry.

Countdowns use `departure_deadline - replay_at`, never the computer's present date. Navigation preserves the current frame, zone and primary/backup choice. Reload starts a new demo session; optional `?zone=11&route=backup&frame=prepare` seeds its initial selection. These URL parameters are startup inputs, not a continuously synchronized router.

See [Phase 1 handoff](docs/phase-1.md) for the unchanged replay's consistency rules and remaining mock behavior, and [data/README.md](data/README.md) for the separate Phase 2 inputs and reproduction commands.
