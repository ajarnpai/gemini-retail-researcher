"""Google Places Details script.

CLI: python scripts/places_details.py --place-ids "ChIJ1" "ChIJ2" [--output path.json]

Fetches place details from Google Places API (New) for up to 10 specific place IDs.
Per-ID caching via cache_manager.py. Requires GOOGLE_PLACES_API_KEY environment variable.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Import config values from sibling config.py via sys.path manipulation
sys.path.insert(0, str(SCRIPT_DIR))
from config import DETAILS_CACHE_TTL_SECONDS, MAX_PLACE_IDS_PER_CALL  # noqa: E402


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


def _set_cache(key: str, data: dict, ttl: int = DETAILS_CACHE_TTL_SECONDS) -> None:
    """Call cache_manager.py set action via subprocess."""
    cache_manager = SCRIPT_DIR / "cache_manager.py"
    subprocess.run(
        [
            sys.executable,
            str(cache_manager),
            "--action", "set",
            "--key", key,
            "--value", json.dumps(data),
            "--ttl", str(ttl),
        ],
        capture_output=True,
        text=True,
    )


def _write_output(output: dict, output_path: str | None) -> None:
    """Print JSON to stdout and optionally write to file."""
    serialized = json.dumps(output, ensure_ascii=False, indent=2)
    print(serialized)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(serialized)


def main():
    parser = argparse.ArgumentParser(description="Fetch place details via Google Places API")
    parser.add_argument(
        "--place-ids", nargs="+", required=True,
        help=f"One or more Google Place IDs to fetch details for (max {MAX_PLACE_IDS_PER_CALL})",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Optional output file path",
    )
    args = parser.parse_args()

    # Validate API key
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        _error("no_api_key", "GOOGLE_PLACES_API_KEY environment variable is not set")

    # Validate number of place IDs
    if len(args.place_ids) > MAX_PLACE_IDS_PER_CALL:
        _error(
            "invalid_query",
            f"Too many place IDs: {len(args.place_ids)} provided, maximum is {MAX_PLACE_IDS_PER_CALL}",
        )


    import requests

    fetched_at = datetime.now(timezone.utc).isoformat()
    results = []

    field_mask = (
        "id,displayName,formattedAddress,location,rating,userRatingCount,"
        "priceLevel,regularOpeningHours,types,websiteUri,nationalPhoneNumber,"
        "editorialSummary,photos,reviews"
    )

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }

    for place_id in args.place_ids:
        cache_key = f"details_{place_id}"
        cached = _get_cached(cache_key)
        cache_status = cached.get("cache_status", "miss")

        if cache_status == "hit" and cached.get("data"):
            place_data = cached["data"]
            place_data["cache_status"] = "hit"
            results.append(place_data)
            continue

        # Fetch from Google Places API
        url = PLACE_DETAILS_URL.format(place_id=place_id)
        try:
            response = requests.get(url, headers=headers, timeout=15)

            if response.ok:
                data = response.json()
                place_data = {
                    "status": "ok",
                    "cache_status": "miss",
                    "place_id": place_id,
                    "details": data,
                    "fetched_at": fetched_at,
                }
                _set_cache(cache_key, place_data, DETAILS_CACHE_TTL_SECONDS)
                results.append(place_data)
            else:
                # Upstream failure — try stale cache fallback
                if cache_status == "stale" and cached.get("data"):
                    place_data = cached["data"]
                    place_data["cache_status"] = "stale"
                    results.append(place_data)
                else:
                    results.append({
                        "status": "error",
                        "place_id": place_id,
                        "error_code": "upstream_unavailable",
                        "message": f"Google Places API returned {response.status_code}: {response.text}",
                    })

        except requests.exceptions.RequestException as exc:
            # Network failure — try stale cache fallback
            if cache_status == "stale" and cached.get("data"):
                place_data = cached["data"]
                place_data["cache_status"] = "stale"
                results.append(place_data)
            else:
                results.append({
                    "status": "error",
                    "place_id": place_id,
                    "error_code": "upstream_unavailable",
                    "message": f"Network error calling Google Places API: {exc}",
                })

    output = {
        "status": "ok",
        "result_count": len(results),
        "results": results,
        "fetched_at": fetched_at,
    }

    _write_output(output, args.output)


if __name__ == "__main__":
    main()
