"""Google Places Nearby Search script.

CLI: python scripts/places_search.py --lat 40.7412 --lng -73.9896 --radius 1.5 --category "clothing_store"
     [--price-tier "mid"] [--area-label "Flatiron"] [--max-results 20] [--output path.json]

Requires GOOGLE_PLACES_API_KEY environment variable.
Uses cache_manager.py (sibling script) for caching via subprocess.
Uses Google Places API (New) endpoint: https://places.googleapis.com/v1/places:searchNearby
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Import config to trigger .env loading into os.environ
import config  # noqa: F401

PLACES_API_URL = "https://places.googleapis.com/v1/places:searchText"
CACHE_TTL = 3600  # 1 hour in seconds
RADIUS_MIN_KM = 0.5
RADIUS_MAX_KM = 10.0
DEFAULT_MAX_RESULTS = 60


def _error(code: str, message: str) -> None:
    """Print a JSON error and exit with code 1."""
    print(json.dumps({"status": "error", "error_code": code, "message": message}))
    sys.exit(1)


def _get_cached(key: str) -> dict:
    """Call cache_manager.py get action via subprocess."""
    cache_manager = SCRIPT_DIR / "cache_manager.py"
    result = subprocess.run(
        [sys.executable, str(cache_manager), "--action", "get", "--key", key],
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "ok", "cache_status": "miss", "data": None}


def _set_cache(key: str, data: dict, ttl: int = CACHE_TTL) -> None:
    """Call cache_manager.py set action via subprocess, using stdin for large payloads."""
    import tempfile
    cache_manager = SCRIPT_DIR / "cache_manager.py"
    value_json = json.dumps(data)
    # Use temp file to avoid Windows command-line length limits
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write(value_json)
    tmp.close()
    subprocess.run(
        [
            sys.executable,
            str(cache_manager),
            "--action", "set",
            "--key", key,
            "--value-file", tmp.name,
            "--ttl", str(ttl),
        ],
        capture_output=True,
        text=True,
    )
    os.unlink(tmp.name)


def _build_cache_key(lat: float, lng: float, radius: float, category: str, price_tier: str | None) -> str:
    """Build a deterministic cache key for this search query."""
    key = f"search_{lat:.4f}_{lng:.4f}_{radius}_{category}"
    if price_tier:
        key += f"_{price_tier}"
    return key


def main():
    parser = argparse.ArgumentParser(description="Search nearby places via Google Places API")
    parser.add_argument("--lat", type=float, required=True, help="Latitude of search center")
    parser.add_argument("--lng", type=float, required=True, help="Longitude of search center")
    parser.add_argument("--radius", type=float, required=True, help="Search radius in km (0.5–10.0)")
    parser.add_argument("--category", type=str, required=True, help="Google Places includedType to search for")
    parser.add_argument("--price-tier", type=str, default=None, help="Price tier filter (e.g. 'mid')")
    parser.add_argument("--area-label", type=str, default=None, help="Human-readable area label")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS, help="Max results to return")
    parser.add_argument("--output", type=str, default=None, help="Optional output file path")
    args = parser.parse_args()

    # Validate API key
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        _error("no_api_key", "GOOGLE_PLACES_API_KEY environment variable is not set")

    # Validate radius
    if args.radius < RADIUS_MIN_KM or args.radius > RADIUS_MAX_KM:
        _error(
            "invalid_query",
            f"radius must be between {RADIUS_MIN_KM} and {RADIUS_MAX_KM} km, got {args.radius}",
        )

    # Build cache key
    cache_key = _build_cache_key(args.lat, args.lng, args.radius, args.category, args.price_tier)

    # Check cache
    cached = _get_cached(cache_key)
    cache_status = cached.get("cache_status", "miss")

    if cache_status == "hit" and cached.get("data"):
        output = cached["data"]
        output["cache_status"] = "hit"
        _write_output(output, args.output)
        return

    # Import requests only when needed (cache miss or stale)
    import requests

    # Build Google Places API request
    radius_meters = args.radius * 1000.0
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        # Atmosphere tier ($0.04/request) — get all fields since we're already
        # paying the highest tier.
        "X-Goog-FieldMask": "places.*,nextPageToken",
    }

    fetched_at = datetime.now(timezone.utc).isoformat()
    places = []
    page_token = None

    try:
        while len(places) < args.max_results:
            request_body = {
                "textQuery": args.category,
                "includedType": args.category,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": args.lat, "longitude": args.lng},
                        "radius": radius_meters,
                    }
                },
                "maxResultCount": min(args.max_results - len(places), 20),
            }
            
            if page_token:
                request_body["pageToken"] = page_token

            response = requests.post(PLACES_API_URL, json=request_body, headers=headers, timeout=15)

            if response.status_code == 429:
                # Rate limited — try stale cache fallback
                if cache_status == "stale" and cached.get("data"):
                    output = cached["data"]
                    output["cache_status"] = "stale"
                    _write_output(output, args.output)
                    return
                _error("rate_limited", "Google Places API rate limit exceeded")

            if response.status_code == 400:
                _error("invalid_query", f"Google Places API returned 400: {response.text}")

            if not response.ok:
                # Upstream failure — try stale cache fallback
                if cache_status == "stale" and cached.get("data"):
                    output = cached["data"]
                    output["cache_status"] = "stale"
                    _write_output(output, args.output)
                    return
                _error(
                    "upstream_unavailable",
                    f"Google Places API returned {response.status_code}: {response.text}",
                )

            data = response.json()
            new_places = data.get("places", [])
            places.extend(new_places)
            
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    except requests.exceptions.RequestException as exc:
        # Network failure — try stale cache fallback
        if cache_status == "stale" and cached.get("data"):
            output = cached["data"]
            output["cache_status"] = "stale"
            _write_output(output, args.output)
            return
        _error("upstream_unavailable", f"Network error calling Google Places API: {exc}")

    # Build query metadata
    query_meta = {
        "lat": args.lat,
        "lng": args.lng,
        "radius_km": args.radius,
        "category": args.category,
    }
    if args.price_tier:
        query_meta["price_tier"] = args.price_tier
    if args.area_label:
        query_meta["area_label"] = args.area_label

    result_count = len(places)

    output = {
        "status": "ok",
        "cache_status": "miss",
        "result_count": result_count,
        "results": places,
        "query": query_meta,
        "fetched_at": fetched_at,
    }

    # Warn on no results or insufficient data
    if result_count == 0:
        output["warning"] = "no_results"
        output["warning_message"] = "No results returned from Google Places API"
    elif result_count < 2:
        output["warning"] = "insufficient_data"
        output["warning_message"] = "Fewer than 2 results returned; data may be insufficient"

    # Cache the result
    _set_cache(cache_key, output)

    _write_output(output, args.output)


def _write_output(output: dict, output_path: str | None) -> None:
    """Print JSON to stdout and optionally write to file."""
    serialized = json.dumps(output, ensure_ascii=True, indent=2)
    sys.stdout.buffer.write(serialized.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
