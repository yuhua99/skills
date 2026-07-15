---
name: google-map
description: Google Maps place search, details/hours, route and travel time, multi-stop itinerary, or KML for My Maps. Use for restaurants, attractions, addresses, commute, trip planning, or map export even when the user does not name Google Maps or its APIs. Results are localized to zh-TW.
---

Use the bundled CLI at `scripts/map_cli.py`, resolved relative to this `SKILL.md` (not the caller's cwd).

Commands: `search_places` · `get_place` · `calculate_route` · `generate_kml_file`. The CLI owns Places API, Routes API, and `MAPS_API_KEY`. Call the CLI only — never raw Google APIs, field masks, language, page size, or location-bias knobs.

## Built-in behavior

- Locale: `zh-TW`. Units: metric. `search_places` returns ≤5 hits; need broader coverage → issue more specific queries.
- **place_id-first**: once you have a `place_id`, reuse it over free-form address text.
- **disambiguate**: when multiple hits are plausible, list 2–5 candidates (name + address) and wait; do not guess.
- **confirmed coordinates**: call `generate_kml_file` only after places and coordinates are confirmed.

## Workflow

1. Vague place name → `search_places`. Done when a single place is chosen (or disambiguated with the user).
2. Hours, phone, website, or map URL → `get_place <place_id>`. Done when the requested fields are in hand.
3. Travel time or distance → `calculate_route`. Mode comparison → one call per `--mode`, then compare durations. Done when distance + duration (per mode) are reported.
4. Multi-stop itinerary → resolve every stop (`search_places` / `place_id`), `get_place` when timing matters, `calculate_route` between consecutive stops. Done when every stop is resolved, every leg has time/distance, and the summary states whether the plan fits the user's time window (or says the window is unknown).
5. Importable map → `generate_kml_file` with confirmed coordinates. Done when `file_path` is returned to the user.

## Commands

Paths relative to this `SKILL.md`.

### `search_places`

```bash
python3 scripts/map_cli.py search_places "<query>"
python3 scripts/map_cli.py search_places "<query>" --near "<near>"
python3 scripts/map_cli.py search_places "<query>" --open-now
```

- `query`: place / restaurant / attraction / address-like text
- `near`: optional place name, address, or `lat,lng`
- `open_now`: optional currently-open filter

Read first: `results[].name`, `place_id`, `formatted_address`, `location`, `rating`, `google_maps_url`.

### `get_place`

```bash
python3 scripts/map_cli.py get_place "<place_id>"
```

Read first: `name`, `formatted_address`, `opening_hours.open_now`, `opening_hours.weekday_text`, `formatted_phone_number`, `website`, `url`, `rating`.

### `calculate_route`

```bash
python3 scripts/map_cli.py calculate_route "<origin>" "<destination>"
python3 scripts/map_cli.py calculate_route "<origin>" "<destination>" --mode transit
python3 scripts/map_cli.py calculate_route "<origin>" "<destination>" --mode driving --depart-at now
```

- `origin` / `destination`: `place_id`, address, or `lat,lng`
- `mode`: `driving` | `walking` | `bicycling` | `transit`
- `depart_at`: optional `now` | Unix timestamp | ISO-8601/RFC3339

Read first: `summary.distance_text`, `summary.duration_text`, `summary.duration_seconds`, `summary.static_duration_seconds`, `summary.warnings`, `legs[].steps[].instruction`, `polyline`.

### `generate_kml_file`

JSON via stdin or `--input`.

```bash
python3 scripts/map_cli.py generate_kml_file --input <json-file>
```

```json
{
  "document_name": "Tokyo Plan",
  "places": [
    {
      "name": "Tokyo Tower",
      "description": "Landmark",
      "coordinates": { "lat": 35.6586, "lng": 139.7454 }
    }
  ],
  "route": {
    "name": "Day 1 Route",
    "description": "Optional route polyline",
    "coordinates": [
      { "lat": 35.6586, "lng": 139.7454 },
      { "lat": 35.6764, "lng": 139.6993 }
    ]
  },
  "file_path": "./tokyo-plan.kml"
}
```

Read first: `file_path`, `bytes_written`, `placemark_count`, `has_route`.

## Response

- Summarize; dump raw JSON only if asked.
- Search hits: name + address. Routes: distance + duration.
- API key errors → tell the user `MAPS_API_KEY` is missing or invalid.

## Failures

1. Check `MAPS_API_KEY`.
2. Empty search → simpler or more specific query; may need a prior `search_places` before `get_place` / route.
3. Empty route → no route for that origin, destination, and mode.
