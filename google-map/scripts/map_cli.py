#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


MAPS_API_KEY_ENV = "MAPS_API_KEY"
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_PLACE_URL = "https://places.googleapis.com/v1/places"
ROUTES_COMPUTE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

DEFAULT_LANGUAGE_CODE = "zh-TW"
DEFAULT_UNITS = "METRIC"
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_NEAR_RADIUS_METERS = 5000.0

SEARCH_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.name",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.types",
        "places.primaryType",
        "places.businessStatus",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.currentOpeningHours",
        "places.googleMapsUri",
    ]
)

PLACE_DETAILS_FIELD_MASK = ",".join(
    [
        "id",
        "name",
        "displayName",
        "formattedAddress",
        "location",
        "businessStatus",
        "currentOpeningHours",
        "regularOpeningHours",
        "nationalPhoneNumber",
        "internationalPhoneNumber",
        "websiteUri",
        "googleMapsUri",
        "rating",
        "userRatingCount",
        "priceLevel",
        "types",
        "primaryType",
    ]
)

ROUTES_FIELD_MASK = ",".join(
    [
        "routes.distanceMeters",
        "routes.duration",
        "routes.staticDuration",
        "routes.polyline.encodedPolyline",
        "routes.warnings",
        "routes.localizedValues.distance.text",
        "routes.localizedValues.duration.text",
        "routes.localizedValues.staticDuration.text",
        "routes.legs.distanceMeters",
        "routes.legs.duration",
        "routes.legs.staticDuration",
        "routes.legs.startLocation",
        "routes.legs.endLocation",
        "routes.legs.localizedValues.distance.text",
        "routes.legs.localizedValues.duration.text",
        "routes.legs.localizedValues.staticDuration.text",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.startLocation",
        "routes.legs.steps.endLocation",
        "routes.legs.steps.navigationInstruction.instructions",
        "routes.legs.steps.localizedValues.distance.text",
        "routes.legs.steps.localizedValues.staticDuration.text",
        "geocodingResults",
    ]
)


class CliError(Exception):
    pass


def fail(message: str, exit_code: int = 1) -> None:
    print(json.dumps({"error": message}, ensure_ascii=False, indent=2), file=sys.stderr)
    raise SystemExit(exit_code)


def require_api_key() -> str:
    api_key = os.getenv(MAPS_API_KEY_ENV)
    if not api_key:
        raise CliError(f"Missing environment variable `{MAPS_API_KEY_ENV}`.")
    return api_key


def request_json(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    encoded_body = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = Request(url, data=encoded_body, headers=request_headers, method=method)
    try:
        with urlopen(request) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise CliError(f"Google Maps API HTTP {exc.code}: {body_text}") from exc
    except URLError as exc:
        raise CliError(f"Failed to reach Google Maps API: {exc.reason}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid JSON response from Google Maps API: {exc}") from exc


def with_query_params(url: str, params: dict[str, Any]) -> str:
    filtered = {key: value for key, value in params.items() if value is not None}
    if not filtered:
        return url
    return f"{url}?{urlencode(filtered)}"


def looks_like_lat_lng(value: str) -> bool:
    return bool(re.fullmatch(r"\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*", value))


def parse_lat_lng(value: str) -> tuple[float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise CliError("Expected `lat,lng` format.")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise CliError("Latitude and longitude must be numeric.") from exc


def looks_like_place_id(value: str) -> bool:
    candidate = value.strip()
    return (
        bool(re.fullmatch(r"[A-Za-z0-9_\-]{20,}", candidate))
        and " " not in candidate
        and "," not in candidate
    )


def point_from_location(value: str) -> dict[str, Any]:
    stripped = value.strip()
    if looks_like_place_id(stripped):
        return {"placeId": stripped}
    if looks_like_lat_lng(stripped):
        lat, lng = parse_lat_lng(stripped)
        return {"location": {"latLng": {"latitude": lat, "longitude": lng}}}
    return {"address": stripped}


def normalize_location(value: dict[str, Any] | None) -> dict[str, float] | None:
    if not value:
        return None
    lat_lng = value.get("latLng") or value
    latitude = lat_lng.get("latitude")
    longitude = lat_lng.get("longitude")
    if latitude is None or longitude is None:
        return None
    return {"lat": latitude, "lng": longitude}


def parse_duration_seconds(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)s", value)
    if not match:
        return None
    return int(float(match.group(1)))


def place_name_text(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    return value.get("text")


def build_search_body(args: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {
        "textQuery": args.query,
        "languageCode": DEFAULT_LANGUAGE_CODE,
        "pageSize": DEFAULT_SEARCH_LIMIT,
    }
    if args.open_now:
        body["openNow"] = True
    if args.near:
        if looks_like_lat_lng(args.near):
            lat, lng = parse_lat_lng(args.near)
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": DEFAULT_NEAR_RADIUS_METERS,
                }
            }
        else:
            body["textQuery"] = f"{args.query} near {args.near}"
    return body


def command_search_places(args: argparse.Namespace) -> dict[str, Any]:
    response = request_json(
        "POST",
        PLACES_TEXT_SEARCH_URL,
        body=build_search_body(args),
        headers={
            "X-Goog-Api-Key": require_api_key(),
            "X-Goog-FieldMask": SEARCH_FIELD_MASK,
        },
    )
    places = []
    for item in (response.get("places") or [])[:DEFAULT_SEARCH_LIMIT]:
        current_hours = item.get("currentOpeningHours") or {}
        places.append(
            {
                "name": place_name_text(item.get("displayName")),
                "place_id": item.get("id"),
                "resource_name": item.get("name"),
                "formatted_address": item.get("formattedAddress"),
                "location": normalize_location(item.get("location")),
                "types": item.get("types") or [],
                "primary_type": item.get("primaryType"),
                "business_status": item.get("businessStatus"),
                "rating": item.get("rating"),
                "user_ratings_total": item.get("userRatingCount"),
                "price_level": item.get("priceLevel"),
                "open_now": current_hours.get("openNow"),
                "google_maps_url": item.get("googleMapsUri"),
            }
        )
    return {"results": places, "count": len(places)}


def normalize_opening_hours(place: dict[str, Any]) -> dict[str, Any] | None:
    current = place.get("currentOpeningHours") or {}
    regular = place.get("regularOpeningHours") or {}
    if not current and not regular:
        return None
    return {
        "open_now": current.get("openNow"),
        "weekday_text": regular.get("weekdayDescriptions")
        or current.get("weekdayDescriptions"),
        "periods": regular.get("periods") or current.get("periods"),
    }


def command_get_place(args: argparse.Namespace) -> dict[str, Any]:
    place_id = args.place_id.strip()
    response = request_json(
        "GET",
        with_query_params(
            f"{PLACES_PLACE_URL}/{quote(place_id)}",
            {"languageCode": DEFAULT_LANGUAGE_CODE},
        ),
        headers={
            "X-Goog-Api-Key": require_api_key(),
            "X-Goog-FieldMask": PLACE_DETAILS_FIELD_MASK,
        },
    )
    return {
        "place_id": response.get("id"),
        "resource_name": response.get("name"),
        "name": place_name_text(response.get("displayName")),
        "formatted_address": response.get("formattedAddress"),
        "location": normalize_location(response.get("location")),
        "business_status": response.get("businessStatus"),
        "opening_hours": normalize_opening_hours(response),
        "formatted_phone_number": response.get("nationalPhoneNumber"),
        "international_phone_number": response.get("internationalPhoneNumber"),
        "website": response.get("websiteUri"),
        "url": response.get("googleMapsUri"),
        "rating": response.get("rating"),
        "user_ratings_total": response.get("userRatingCount"),
        "price_level": response.get("priceLevel"),
        "types": response.get("types") or [],
        "primary_type": response.get("primaryType"),
    }


def format_departure_time(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if stripped == "now":
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    if re.fullmatch(r"\d+", stripped):
        return (
            datetime.fromtimestamp(int(stripped), tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    try:
        normalized = stripped.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CliError(
            "`depart_at` must be `now`, a Unix timestamp, or an ISO-8601/RFC3339 datetime."
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_route_body(args: argparse.Namespace) -> dict[str, Any]:
    travel_mode_map = {
        "driving": "DRIVE",
        "walking": "WALK",
        "bicycling": "BICYCLE",
        "transit": "TRANSIT",
    }
    body: dict[str, Any] = {
        "origin": point_from_location(args.origin),
        "destination": point_from_location(args.destination),
        "travelMode": travel_mode_map[args.mode],
        "languageCode": DEFAULT_LANGUAGE_CODE,
        "units": DEFAULT_UNITS,
        "polylineQuality": "OVERVIEW",
        "polylineEncoding": "ENCODED_POLYLINE",
    }
    departure_time = format_departure_time(args.depart_at)
    if departure_time:
        body["departureTime"] = departure_time
    if args.mode == "driving":
        body["routingPreference"] = "TRAFFIC_AWARE"
    return body


def localized_text(container: dict[str, Any] | None, key: str) -> str | None:
    if not container:
        return None
    value = container.get(key) or {}
    return value.get("text")


def normalize_geocoding_results(
    results: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not results:
        return None
    normalized: dict[str, Any] = {}
    for key in ("origin", "destination"):
        item = results.get(key)
        if item:
            normalized[key] = {
                "place_id": item.get("placeId"),
                "types": item.get("type") or [],
            }
    intermediates = []
    for item in results.get("intermediates") or []:
        intermediates.append(
            {
                "place_id": item.get("placeId"),
                "types": item.get("type") or [],
                "request_index": item.get("intermediateWaypointRequestIndex"),
            }
        )
    if intermediates:
        normalized["intermediates"] = intermediates
    return normalized or None


def summarize_step(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "instruction": ((step.get("navigationInstruction") or {}).get("instructions"))
        or "",
        "distance_text": localized_text(step.get("localizedValues"), "distance"),
        "duration_text": localized_text(step.get("localizedValues"), "staticDuration"),
        "start_location": normalize_location(step.get("startLocation")),
        "end_location": normalize_location(step.get("endLocation")),
    }


def summarize_leg(leg: dict[str, Any]) -> dict[str, Any]:
    return {
        "distance_meters": leg.get("distanceMeters"),
        "distance_text": localized_text(leg.get("localizedValues"), "distance"),
        "duration_seconds": parse_duration_seconds(leg.get("duration")),
        "duration_text": localized_text(leg.get("localizedValues"), "duration"),
        "static_duration_seconds": parse_duration_seconds(leg.get("staticDuration")),
        "start_location": normalize_location(leg.get("startLocation")),
        "end_location": normalize_location(leg.get("endLocation")),
        "steps": [summarize_step(step) for step in (leg.get("steps") or [])],
    }


def command_calculate_route(args: argparse.Namespace) -> dict[str, Any]:
    response = request_json(
        "POST",
        ROUTES_COMPUTE_URL,
        body=build_route_body(args),
        headers={
            "X-Goog-Api-Key": require_api_key(),
            "X-Goog-FieldMask": ROUTES_FIELD_MASK,
        },
    )
    routes = response.get("routes") or []
    if not routes:
        return {
            "summary": None,
            "legs": [],
            "polyline": None,
            "geocoding_results": normalize_geocoding_results(
                response.get("geocodingResults")
            ),
        }

    route = routes[0]
    legs = route.get("legs") or []
    first_leg = legs[0] if legs else {}
    last_leg = legs[-1] if legs else {}
    return {
        "summary": {
            "origin": args.origin,
            "destination": args.destination,
            "mode": args.mode,
            "distance_meters": route.get("distanceMeters", 0),
            "distance_text": localized_text(route.get("localizedValues"), "distance"),
            "duration_seconds": parse_duration_seconds(route.get("duration")) or 0,
            "duration_text": localized_text(route.get("localizedValues"), "duration"),
            "static_duration_seconds": parse_duration_seconds(
                route.get("staticDuration")
            ),
            "start_location": normalize_location(first_leg.get("startLocation")),
            "end_location": normalize_location(last_leg.get("endLocation")),
            "warnings": route.get("warnings") or [],
        },
        "legs": [summarize_leg(leg) for leg in legs],
        "polyline": ((route.get("polyline") or {}).get("encodedPolyline")),
        "geocoding_results": normalize_geocoding_results(
            response.get("geocodingResults")
        ),
    }


def json_input(path_value: str | None) -> dict[str, Any]:
    try:
        raw = (
            Path(path_value).read_text(encoding="utf-8")
            if path_value
            else sys.stdin.read()
        )
    except OSError as exc:
        source = f"`{path_value}`" if path_value else "stdin"
        raise CliError(f"Failed to read JSON input from {source}: {exc}") from exc
    if not raw.strip():
        raise CliError("Expected JSON input from `--input` file or stdin.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid JSON input: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("Top-level JSON input must be an object.")
    return payload


def slugify_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return slug or "map-export"


def kml_coordinates_string(coordinates: list[dict[str, Any]]) -> str:
    pairs: list[str] = []
    for coordinate in coordinates:
        if not isinstance(coordinate, dict):
            raise CliError("Each route coordinate must be an object.")
        lat = coordinate.get("lat")
        lng = coordinate.get("lng")
        if lat is None or lng is None:
            raise CliError("Each coordinate requires `lat` and `lng`.")
        pairs.append(f"{lng},{lat},0")
    return " ".join(pairs)


def indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "  "
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = "\n" + indent * (level + 1)
        for child in children:
            indent_xml(child, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = "\n" + indent * level
    if level and (not element.tail or not element.tail.strip()):
        element.tail = "\n" + indent * level


def command_generate_kml_file(args: argparse.Namespace) -> dict[str, Any]:
    payload = json_input(args.input)
    document_name = payload.get("document_name")
    places = payload.get("places")
    route = payload.get("route")

    if not isinstance(document_name, str) or not document_name.strip():
        raise CliError("`document_name` is required.")
    if not isinstance(places, list) or not places:
        raise CliError("`places` must be a non-empty array.")

    file_path = payload.get("file_path") or f"./{slugify_filename(document_name)}.kml"
    if not isinstance(file_path, str) or not file_path.strip():
        raise CliError("`file_path` must be a string when provided.")

    root = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(root, "Document")
    ET.SubElement(document, "name").text = document_name

    for place in places:
        if not isinstance(place, dict):
            raise CliError("Each `places[]` item must be an object.")
        name = place.get("name")
        coordinates = place.get("coordinates")
        if not isinstance(name, str) or not name.strip():
            raise CliError("Each place requires `name`.")
        if not isinstance(coordinates, dict):
            raise CliError("Each place requires `coordinates`.")
        lat = coordinates.get("lat")
        lng = coordinates.get("lng")
        if lat is None or lng is None:
            raise CliError("Each place coordinate requires `lat` and `lng`.")

        placemark = ET.SubElement(document, "Placemark")
        ET.SubElement(placemark, "name").text = name
        if isinstance(place.get("description"), str) and place.get("description"):
            ET.SubElement(placemark, "description").text = place["description"]
        point = ET.SubElement(placemark, "Point")
        ET.SubElement(point, "coordinates").text = f"{lng},{lat},0"

    has_route = False
    if route is not None:
        if not isinstance(route, dict):
            raise CliError("`route` must be an object when provided.")
        coordinates = route.get("coordinates")
        if coordinates:
            if not isinstance(coordinates, list):
                raise CliError("`route.coordinates` must be an array.")
            has_route = True
            placemark = ET.SubElement(document, "Placemark")
            ET.SubElement(placemark, "name").text = str(route.get("name") or "Route")
            if isinstance(route.get("description"), str) and route.get("description"):
                ET.SubElement(placemark, "description").text = route["description"]
            line_string = ET.SubElement(placemark, "LineString")
            ET.SubElement(line_string, "tessellate").text = "1"
            ET.SubElement(line_string, "coordinates").text = kml_coordinates_string(
                coordinates
            )

    indent_xml(root)
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output_path = Path(file_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(xml_bytes)
    except OSError as exc:
        raise CliError(f"Failed to write KML file `{output_path}`: {exc}") from exc

    return {
        "file_path": str(output_path),
        "bytes_written": output_path.stat().st_size,
        "placemark_count": len(places),
        "has_route": has_route,
        "preview": "\n".join(xml_bytes.decode("utf-8").splitlines()[:8]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Google Maps skill-oriented CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search_places", help="Search places")
    search.add_argument("query")
    search.add_argument("--near")
    search.add_argument("--open-now", action="store_true")
    search.set_defaults(handler=command_search_places)

    get_place = subparsers.add_parser("get_place", help="Get place details")
    get_place.add_argument("place_id")
    get_place.set_defaults(handler=command_get_place)

    route = subparsers.add_parser("calculate_route", help="Calculate a route")
    route.add_argument("origin")
    route.add_argument("destination")
    route.add_argument(
        "--mode",
        default="driving",
        choices=["driving", "walking", "bicycling", "transit"],
    )
    route.add_argument("--depart-at")
    route.set_defaults(handler=command_calculate_route)

    kml = subparsers.add_parser(
        "generate_kml_file", help="Generate a KML file from JSON input"
    )
    kml.add_argument("--input", help="JSON input file path; reads stdin if omitted")
    kml.set_defaults(handler=command_generate_kml_file)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result: dict[str, Any] = {}
    try:
        result = args.handler(args)
    except CliError as exc:
        fail(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
