"""Parse location inputs into canonical lat/lng coordinates.

Accepts:
  --lat <f> --lng <f>          Explicit coordinates
  --input "<string>"           Coordinate string, Google Maps URL, or configured alias

Outputs JSON to stdout:
  {"status": "ok", "lat": float, "lng": float, "input_type": "...", "raw_input": "..."}
  {"status": "error", "error_code": "invalid_location_input", "message": "..."}
"""

import argparse
import json
import re
import sys
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from config import KNOWN_LOCATION_ALIASES


def _validate_coords(lat: float, lng: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lng <= 180


def _parse_coordinate_string(value: str):
    match = re.match(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$", value)
    if not match:
        return None
    lat, lng = float(match.group(1)), float(match.group(2))
    if _validate_coords(lat, lng):
        return lat, lng
    return None


def _parse_google_maps_url(value: str):
    patterns = [
        r"/@(-?\d+\.?\d+),(-?\d+\.?\d+)",
        r"[?&]q=(-?\d+\.?\d+),(-?\d+\.?\d+)",
        r"[?&]ll=(-?\d+\.?\d+),(-?\d+\.?\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        lat, lng = float(match.group(1)), float(match.group(2))
        if _validate_coords(lat, lng):
            return lat, lng
    return None


def _is_google_maps_url(value: str) -> bool:
    host = urlparse(value).netloc.lower()
    return any(
        token in host
        for token in ("google.com", "goo.gl", "maps.app.goo.gl")
    )


def _resolve_google_maps_shortlink(value: str):
    host = urlparse(value).netloc.lower()
    if "maps.app.goo.gl" not in host:
        return value
    request = Request(
        value,
        headers={"User-Agent": "Mozilla/5.0"},
        method="GET",
    )
    with urlopen(request, timeout=15) as response:
        return response.geturl()


def _parse_alias(value: str):
    key = value.strip().lower().replace(" ", "_")
    coords = KNOWN_LOCATION_ALIASES.get(key)
    if not coords:
        return None
    lat = coords.get("lat")
    lng = coords.get("lng")
    if lat is None or lng is None:
        return None
    if _validate_coords(lat, lng):
        return lat, lng
    return None


def _success(lat, lng, input_type, raw_input):
    return {
        "status": "ok",
        "lat": lat,
        "lng": lng,
        "input_type": input_type,
        "raw_input": raw_input,
    }


def _error(message):
    return {
        "status": "error",
        "error_code": "invalid_location_input",
        "message": message,
    }


def main():
    parser = argparse.ArgumentParser(description="Parse location input to lat/lng")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lng", type=float)
    parser.add_argument("--input", dest="location_input", type=str)
    args = parser.parse_args()

    if args.lat is not None and args.lng is not None:
        if not _validate_coords(args.lat, args.lng):
            print(json.dumps(_error(f"Coordinates out of range: lat={args.lat}, lng={args.lng}")))
            sys.exit(1)
        print(json.dumps(_success(args.lat, args.lng, "explicit", f"{args.lat},{args.lng}")))
        sys.exit(0)

    if args.location_input:
        raw = args.location_input
        if _is_google_maps_url(raw):
            try:
                resolved = _resolve_google_maps_shortlink(raw)
            except URLError as exc:
                print(
                    json.dumps(
                        _error(
                            f"Could not resolve Google Maps short URL '{raw}': {exc.reason}"
                        )
                    )
                )
                sys.exit(1)
            coords = _parse_google_maps_url(resolved)
            if coords:
                print(json.dumps(_success(coords[0], coords[1], "google_maps_url", raw)))
                sys.exit(0)
        coords = _parse_coordinate_string(raw)
        if coords:
            print(json.dumps(_success(coords[0], coords[1], "coordinate_string", raw)))
            sys.exit(0)
        coords = _parse_alias(raw)
        if coords:
            print(json.dumps(_success(coords[0], coords[1], "location_alias", raw)))
            sys.exit(0)
        message = (
            f"Could not parse location from '{raw}'. Provide coordinates like '40.7412,-73.9896', "
            "a Google Maps URL, or a configured alias."
        )
        print(json.dumps(_error(message)))
        sys.exit(1)

    print(json.dumps(_error("No location input provided. Use --lat/--lng or --input.")))
    sys.exit(1)


if __name__ == "__main__":
    main()
