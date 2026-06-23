---
name: google-map
description: Use this skill whenever the user needs Google Maps based place search, place details, opening hours, route planning, travel time estimation, multi-stop itinerary checking, or KML export for Google My Maps. Trigger it for requests about restaurants, attractions, addresses, commute comparison, trip planning, and map export even when the user does not explicitly say Google Maps, Places API, Routes API, or KML.
---

Use the bundled CLI at `scripts/map_cli.py`, resolved relative to this `SKILL.md` file rather than assuming the current working directory is the repo root.

When running commands from another working directory, first resolve the directory containing `SKILL.md`, then invoke `scripts/map_cli.py` from there.

This skill is a high-level wrapper around four commands:

- `search_places`
- `get_place`
- `calculate_route`
- `generate_kml_file`

The CLI already handles:

- Places API
- Routes API
- `MAPS_API_KEY` from the environment

Do not bypass the CLI with direct Google API calls unless the CLI clearly cannot do the task.

## What to expose

Keep the interaction high level. Only use these inputs:

- `search_places(query, near?, open_now?)`
- `get_place(place_id)`
- `calculate_route(origin, destination, mode?, depart_at?)`
- `generate_kml_file(document_name, places, route?, file_path?)`

Do not introduce low-level Google parameters such as field masks, routing preferences, language settings, page size, or location bias tuning.

## Core workflow

1. If the user names a place vaguely, run `search_places` first.
2. If the user needs hours, phone, website, or map URL, run `get_place` on the chosen `place_id`.
3. If the user needs travel time or distance, run `calculate_route`.
4. If the user wants an importable map file, collect confirmed coordinates and run `generate_kml_file`.

Prefer reusing `place_id` once you have it. It is more reliable than free-form address text.

## Command usage

All example paths are relative to this `SKILL.md` file, not the caller's current working directory.

### `search_places`

Use for place discovery.

```bash
python3 scripts/map_cli.py search_places "<query>"
python3 scripts/map_cli.py search_places "<query>" --near "<near>"
python3 scripts/map_cli.py search_places "<query>" --open-now
```

Inputs:

- `query`: place, restaurant, attraction, or address-like search text
- `near`: optional place name, address, or `lat,lng`
- `open_now`: optional filter for currently open places

Read these fields first:

- `results[].name`
- `results[].place_id`
- `results[].formatted_address`
- `results[].location`
- `results[].rating`
- `results[].google_maps_url`

When multiple results are plausible, present a short disambiguation list instead of guessing.

### `get_place`

Use for detailed place information.

```bash
python3 scripts/map_cli.py get_place "<place_id>"
```

Read these fields first:

- `name`
- `formatted_address`
- `opening_hours.open_now`
- `opening_hours.weekday_text`
- `formatted_phone_number`
- `website`
- `url`
- `rating`

Use this when the user asks whether a place is open, asks for contact info, or wants the official map link.

### `calculate_route`

Use for travel time, distance, and route guidance.

```bash
python3 scripts/map_cli.py calculate_route "<origin>" "<destination>"
python3 scripts/map_cli.py calculate_route "<origin>" "<destination>" --mode transit
python3 scripts/map_cli.py calculate_route "<origin>" "<destination>" --mode driving --depart-at now
```

Inputs:

- `origin`: `place_id`, address, or `lat,lng`
- `destination`: `place_id`, address, or `lat,lng`
- `mode`: `driving`, `walking`, `bicycling`, or `transit`
- `depart_at`: optional `now`, Unix timestamp, or ISO-8601/RFC3339 datetime

Read these fields first:

- `summary.distance_text`
- `summary.duration_text`
- `summary.duration_seconds`
- `summary.static_duration_seconds`
- `summary.warnings`
- `legs[].steps[].instruction`
- `polyline`

If the user asks for mode comparison, run the command multiple times with different `--mode` values and compare the durations clearly.

### `generate_kml_file`

Use for Google My Maps export.

The command reads JSON from stdin or from `--input`.

```bash
python3 scripts/map_cli.py generate_kml_file --input <json-file>
```

Expected payload shape:

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

Read these fields first:

- `file_path`
- `bytes_written`
- `placemark_count`
- `has_route`

Only call this after the places and coordinates are already confirmed.

## Recommended patterns

### Place lookup

1. Search with the user's phrase.
2. If needed, show 2-5 likely candidates.
3. Reuse the selected `place_id` downstream.

### Trip planning

1. Resolve each stop with `search_places`.
2. Check hours with `get_place` when timing matters.
3. Calculate routes between stops.
4. Summarize whether the plan is realistic.

### Map export

1. Collect finalized places with coordinates.
2. Add route coordinates only if already available.
3. Generate the KML.
4. Return the written file path.

## Response guidance

- Summarize useful results instead of dumping raw JSON unless the user asked for machine-readable output.
- Include place name and address when presenting search hits.
- Include distance and duration when presenting routes.
- Point out ambiguity when results are not clearly unique.
- If the CLI reports an API key problem, tell the user that `MAPS_API_KEY` is missing or invalid.

## Failure handling

If a command fails:

1. Check whether `MAPS_API_KEY` is available.
2. Check whether a prior `search_places` step is needed.
3. If route results are empty, say no route was found for that origin, destination, and mode.
4. If search results are empty, try a simpler or more specific query.

## Examples

User: `Find yakiniku restaurants near Shinjuku that are open right now.`

```bash
python3 scripts/map_cli.py search_places "yakiniku" --near "Shinjuku" --open-now
```

User: `Check whether Tokyo Tower is open today.`

First search if needed, then:

```bash
python3 scripts/map_cli.py get_place "<place_id>"
```

User: `How long does it take to get from Tokyo Station to Asakusa by transit?`

```bash
python3 scripts/map_cli.py calculate_route "Tokyo Station" "Asakusa" --mode transit
```

User: `Create a Google My Maps import file for these attractions.`

Build the JSON payload and run `generate_kml_file`.
