# Dataset validation — delhi_yamuna

**Status: PASS**

Dataset integrity and declared representation only; not operational flood/evacuation validation

| Check | Result | Evidence |
| --- | --- | --- |
| provenance_and_checksums | pass | {"datasets": 11, "unique_files_checksum_verified": 25, "file_references": 28} |
| pilot_boundary | pass | {"bbox_wgs84": [77.215, 28.59, 77.305, 28.715], "area_km2": 121.94393798803375, "metric_crs": "EPSG:32643"} |
| dem | pass | {"valid_pixels": 135488, "minimum": 196.2386016845703, "maximum": 246.2974090576172} |
| population_conservation_and_alignment | pass | {"valid_pixels": 15312, "minimum": 0.002550789242038018, "maximum": 327.99642055436624, "population_total": 2842043.38060584, "partially_known_cells": 0, "source_valid_cell_count": 192, "source_fractional_pilot_total": 2842043.3806058443, "aligned_pilot_total": 2842043.38060584, "absolute_conservation_error": 4.190951585769653e-09, "source_nodata_reinterpreted_as_zero": false} |
| persisted_road_graph | pass | {"nodes": 32239, "edges": 86396, "weak_components": 117, "assumed_speed_edges": 85001} |
| communities | pass | {"features": 85, "representation": ["osm_point"], "unnamed_features": 0, "repeated_name_groups": 1, "physical_entities_deduplicated": false} |
| candidate_sites | pass | {"features": 269, "representation": ["osm_point", "point_on_clipped_osm_geometry"], "unnamed_features": 43, "repeated_name_groups": 5, "physical_entities_deduplicated": false} |
| hydrography | pass | {"features": 143} |
| gauge_reference | pass | {"stations": 1, "documented_observations": 1, "vertical_datum_reconciled": false} |
| historical_flood_evidence | pass | {"nrsc_shantivan": {"visible_pixels": 13142, "classified_flood_mask": false}, "nrsc_shastri_park": {"visible_pixels": 21269, "classified_flood_mask": false}, "map_coverage_fraction_of_pilot": 0.2535190837445131} |

## Limitations

- Study rectangle is an analysis choice, not an administrative or flood boundary.
- Copernicus GLO-30 is a surface model including vegetation/buildings, not bare-earth terrain or river bathymetry.
- Population 2023 is a retrospective model estimate released in 2025, not an event-day census.
- Population is kept at native resolution and conservatively transferred to a 90m grid nested in the 30m DEM grid; this creates no new demographic detail.
- Archived OSM represents mapping known at the snapshot date, not verified field completeness.
- Road speeds are explicit non-flood planning assumptions, not observed July 2023 travel times.
- Localities are representative points, not population boundaries; candidate facilities have unknown capacity and safety.
- NRSC map evidence is not automatically a georeferenced binary inundation mask.
- No Phase 2 data is used by the Phase 1 API or frontend.
- User-approved 1km source replaces the earlier planned 100m source; no further population download is authorized
- Constrained alpha-release population estimate, not census counts or event-day displacement data
- Approximately 1km source cells cannot resolve settlements, roads or flood-edge exposure at 30m/90m scales
- 90m output is alignment-only conservative redistribution assuming uniform population within each approximately 1km source pixel; it adds no information
- Do not bilinearly interpolate person counts or interpret counts as densities
- Original download timestamp and independent publisher checksum were not supplied; local checksum and browser-origin metadata are recorded
- Hydrography includes mapped waterway ways only; natural=water features and multipolygon relations are omitted.
- Localities are mapped place nodes only; candidate facilities are mapped nodes/ways only. Relations are omitted.
- NRSC/CWC public access does not establish an open redistribution licence; NRSC maps are marked For official use.
- NRSC map coverage is partial, with clouds/labels; Shastri Park map date and identifier disagree.
- GeoPDF control fit measures internal registration only, not independent positional accuracy.
- Road graph has disconnected components and omits turn restrictions/conditional access; no flood isolation inference is made.
