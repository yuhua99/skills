# Google Maps Agent Skill

This repository provides an installable skill for AI agents that need to work with Google Maps data through a bundled CLI.

The skill helps an agent:

- search for places
- fetch place details such as opening hours, phone numbers, websites, and map links
- calculate routes, travel time, and distance
- generate KML files for Google My Maps

The bundled CLI uses:

- Places API
- Routes API

## What the skill does

The skill exposes four high-level capabilities:

- `search_places`
- `get_place`
- `calculate_route`
- `generate_kml_file`

It is designed to be used by an AI agent at a high level instead of exposing raw Google API parameters.

## Environment setup

This skill requires a Google Maps API key in the `MAPS_API_KEY` environment variable.

To get a Google Maps API key, create or select a Google Cloud project, enable billing, enable the `Places API` and `Routes API`, then create an API key in Google Cloud Console. For production use, restrict the key to the APIs you need and to your app, server IPs, or HTTP referrers. See the official setup guide: `https://developers.google.com/maps/get-started`

Example:

```bash
export MAPS_API_KEY="your_google_maps_api_key"
```

You should enable the Google APIs required by the bundled CLI in your Google Cloud project.

## Install the skill

Install from GitHub:

```bash
bunx skills add https://github.com/yuhua99/skills/tree/main/google-map
```

If you fork or mirror this repository, replace the URL with your own install source.

## How to use it

After installation, the agent can use this skill for requests like:

- "Find ramen shops near Shinjuku that are open now"
- "Check whether Tokyo Tower is open today"
- "How long does it take to get from Tokyo Station to Asakusa by transit?"
- "Create a Google My Maps import file for these attractions"

The skill uses the bundled CLI at `scripts/map_cli.py` internally.

## Repository contents

- `SKILL.md`: skill definition and behavior guidance
- `scripts/map_cli.py`: bundled CLI implementation
