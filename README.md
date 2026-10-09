# DANGER MARK+ — Flood Consequence & Evacuation Intelligence

Phase 1: the existing `Amazon/` React console reads a deterministic Delhi/Yamuna demo replay from FastAPI through a typed API client. **All operational data is synthetic demonstration data, not verified July 2023 history or operational evacuation guidance.**

The Figma frontend remains in `Amazon/`. Its stylesheet, branding, desktop layout, and Leaflet map stack are preserved. No real flood modelling, routing engine, messaging, database, authentication, or AWS deployment is implemented.

Phase 2 adds a separate [Delhi/Yamuna dataset pipeline](data/README.md): catalogued sources, offline geospatial preprocessing, and validation. The real datasets are not connected to the synthetic replay. See the [Phase 2 handoff](docs/phase-2.md) for the resumed implementation, source inventory, checks, and limitations.

Phase 3 adds a separate [deterministic flood-consequences engine](docs/phase-3.md), with population overlap, road impacts, locality accessibility and run-oriented APIs. Its pilot uses an explicitly hypothetical terrain surface, not a validated historical flood reconstruction. The existing frontend and demo replay remain unchanged. See [computed results](docs/phase-3-results.json) for assumptions, metrics and reproducibility checks.

## Run locally

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

All endpoints are read-only. JSON numbers remain numbers; dates are ISO 8601 with timezone offsets. Presentation formatting lives in the frontend.

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

`models/` and `infra/` remain reserved for later approved work. Large datasets and generated output stay out of Git; only small manifests and validation metadata are tracked. Geospatial preprocessing lives in `scripts/` and does not add dependencies to the replay backend. No database, distributed processing, ML model, or AWS deployment is added.

## Edit the demo

The single source is [`backend/app/fixtures/demo-yamuna-2023.json`](backend/app/fixtures/demo-yamuna-2023.json). Change its numeric values/timestamps and increment `revision`, then refresh the browser or change snapshots. Each API request re-reads and validates the file; no JSX edit or backend restart is needed. Save the complete file before refreshing. The frontend rejects mixed revisions and offers retry.

Countdowns use `departure_deadline - replay_at`, never the computer's present date. Navigation preserves the current frame, zone and primary/backup choice. Reload starts a new demo session; optional `?zone=11&route=backup&frame=prepare` seeds its initial selection. These URL parameters are startup inputs, not a continuously synchronized router.

See [Phase 1 handoff](docs/phase-1.md) for the unchanged replay's consistency rules and remaining mock behavior, and [data/README.md](data/README.md) for the separate Phase 2 inputs and reproduction commands.
