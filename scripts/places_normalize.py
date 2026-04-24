"""Normalize Google Places API (New), CSV, or user-provided JSON data into a generic place schema.

CLI:
    python scripts/places_normalize.py --input <path> [--source google|csv|json]
        [--area-label <label>] [--output <path>]

Output JSON:
    {
        "status": "ok",
        "places": [...],
        "normalization_warnings": [],
        "total_input": N,
        "total_normalized": N,
        "total_dropped": N
    }
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Price-level mapping for Google Places API (New)
# ---------------------------------------------------------------------------
GOOGLE_PRICE_MAP = {
    "PRICE_LEVEL_FREE": "low",
    "PRICE_LEVEL_INEXPENSIVE": "low",
    "PRICE_LEVEL_MODERATE": "mid",
    "PRICE_LEVEL_EXPENSIVE": "high",
    "PRICE_LEVEL_VERY_EXPENSIVE": "high",
}

# ---------------------------------------------------------------------------
# Flexible CSV header aliases
# ---------------------------------------------------------------------------
CSV_FIELD_ALIASES = {
    "place_id": ["place_id", "id", "google_place_id", "place id"],
    "name": ["name", "restaurant_name", "Name", "restaurant name", "title"],
    "primary_category": ["primary_category", "category", "type", "cuisine", "primarytype", "primary type"],
    "rating": ["rating", "avg_rating", "average_rating"],
    "review_count": ["review_count", "reviews", "user_rating_count", "userRatingCount", "review count"],
    "price_level": ["price_level", "price", "pricelevel", "price level"],
    "formatted_address": ["formatted_address", "address", "formattedAddress", "formatted address", "location"],
    "lat": ["lat", "latitude"],
    "lng": ["lng", "longitude", "long"],
    "area_label": ["area_label", "area", "neighborhood", "district"],
    "tags": ["tags", "types", "labels"],
    "summary": ["summary", "description", "notes"],
}

# Aliases for user-provided JSON (same structure)
JSON_FIELD_ALIASES = CSV_FIELD_ALIASES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

def detect_source(path: Path, data) -> str:
    """Auto-detect source format from file extension and content."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        # Google Places API (New) format or our search script output
        if isinstance(data, dict) and ("places" in data or "results" in data):
            return "google"
        return "json"
    # fallback
    if isinstance(data, dict) and ("places" in data or "results" in data):
        return "google"
    return "json"


# ---------------------------------------------------------------------------
# Google Places normalization
# ---------------------------------------------------------------------------

def _extract_text(obj) -> str | None:
    """Extract text from Google's {text, languageCode} objects."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return obj.get("text")
    return None


def _extract_area_label(raw: dict, override_area_label: str | None) -> str | None:
    if override_area_label:
        return override_area_label

    components = raw.get("addressComponents")
    if isinstance(components, list):
        preferred_types = [
            "sublocality_level_2",
            "sublocality_level_1",
            "locality",
            "administrative_area_level_2",
            "administrative_area_level_1",
        ]
        for component_type in preferred_types:
            for component in components:
                if component_type in (component.get("types") or []):
                    label = component.get("shortText") or component.get("longText")
                    if label:
                        return label

    descriptor = raw.get("addressDescriptor") or {}
    areas = descriptor.get("areas") if isinstance(descriptor, dict) else None
    if isinstance(areas, list):
        preferred = sorted(
            (
                area for area in areas
                if isinstance(area, dict) and area.get("displayName")
            ),
            key=lambda area: (
                {"WITHIN": 0, "OUTSKIRTS": 1, "NEAR": 2}.get(area.get("containment"), 99),
                _extract_text(area.get("displayName")) or "",
            ),
        )
        if preferred:
            label = _extract_text(preferred[0].get("displayName"))
            if label:
                return label

    return None


def _build_google_summary(
    raw: dict,
    name: str | None,
    area_label: str | None,
    editorial: str | None,
    generative: str | None,
) -> str | None:
    if editorial:
        return editorial
    if generative:
        return generative

    type_label = (
        _extract_text(raw.get("googleMapsTypeLabel"))
        or _extract_text(raw.get("primaryTypeDisplayName"))
        or raw.get("primaryType")
    )
    address = raw.get("shortFormattedAddress") or raw.get("formattedAddress")

    if type_label and area_label:
        return f"{type_label} in {area_label}"
    if type_label and address:
        return f"{type_label} at {address}"
    if name and area_label:
        return f"{name} in {area_label}"
    if name and address:
        return f"{name} at {address}"
    return name or type_label or "Place"


def _normalize_google_place(raw: dict, area_label: str | None) -> dict | None:
    """Normalize a single Google Places API (New) record. Returns None if invalid."""
    place_id = raw.get("id")
    if not place_id:
        return None

    name = _extract_text(raw.get("displayName"))

    location = raw.get("location", {}) or {}
    lat = location.get("latitude")
    lng = location.get("longitude")

    price_raw = raw.get("priceLevel")
    price_level = GOOGLE_PRICE_MAP.get(price_raw) if price_raw else None

    tags = list(raw.get("types", []) or [])

    editorial = _extract_text(raw.get("editorialSummary"))
    gen_summary = raw.get("generativeSummary")
    generative = _extract_text(gen_summary.get("overview") if isinstance(gen_summary, dict) else gen_summary)

    effective_area = _extract_area_label(raw, area_label)
    summary = _build_google_summary(raw, name, effective_area, editorial, generative)

    return {
        "place_id": place_id,
        "name": name,
        "primary_category": raw.get("primaryType"),
        "primary_category_display": _extract_text(raw.get("primaryTypeDisplayName")),
        "area_label": effective_area,
        "rating": raw.get("rating"),
        "review_count": raw.get("userRatingCount"),
        "price_level": price_level,
        "price_range": raw.get("priceRange"),
        "formatted_address": raw.get("formattedAddress"),
        "short_address": raw.get("shortFormattedAddress"),
        "lat": lat,
        "lng": lng,
        "tags": tags,
        "business_status": raw.get("businessStatus"),
        "google_maps_uri": raw.get("googleMapsUri"),
        "website_uri": raw.get("websiteUri"),
        "phone": raw.get("nationalPhoneNumber") or raw.get("internationalPhoneNumber"),
        "opening_hours": raw.get("regularOpeningHours"),
        "editorial_summary": editorial,
        "generative_summary": generative,
        "serves_coffee": raw.get("servesCoffee"),
        "serves_breakfast": raw.get("servesBreakfast"),
        "serves_brunch": raw.get("servesBrunch"),
        "serves_lunch": raw.get("servesLunch"),
        "serves_dinner": raw.get("servesDinner"),
        "serves_vegetarian_food": raw.get("servesVegetarianFood"),
        "dine_in": raw.get("dineIn"),
        "takeout": raw.get("takeout"),
        "delivery": raw.get("delivery"),
        "reservable": raw.get("reservable"),
        "outdoor_seating": raw.get("outdoorSeating"),
        "good_for_groups": raw.get("goodForGroups"),
        "reviews": _extract_reviews(raw.get("reviews")),
        "summary": summary,
        "source_fetched_at": _now_iso(),
    }


def _extract_reviews(raw_reviews: list | None) -> list[dict]:
    """Extract reviews from Google Places API response."""
    if not raw_reviews:
        return []
    reviews = []
    for r in raw_reviews:
        author_attr = r.get("authorAttribution", {})
        reviews.append({
            "author_name": author_attr.get("displayName") if isinstance(author_attr, dict) else None,
            "rating": r.get("rating"),
            "text": _extract_text(r.get("text")),
            "original_text": _extract_text(r.get("originalText")),
            "relative_time": r.get("relativePublishTimeDescription"),
        })
    return reviews


def normalize_google(data: dict, area_label: str | None) -> tuple[list, list, list]:
    """Returns (places, warnings, dropped_warnings)."""
    places = []
    warnings = []
    dropped = []

    # Support both raw Google format {"places": [...]} and our search script format {"results": [...]}
    raw_list = data.get("places", data.get("results", []))
    for i, raw in enumerate(raw_list):
        result = _normalize_google_place(raw, area_label)
        if result is None:
            name = (raw.get("displayName") or {}).get("text", f"record[{i}]")
            dropped.append(f"Dropped '{name}': missing place_id")
        else:
            places.append(result)

    return places, warnings, dropped


# ---------------------------------------------------------------------------
# CSV normalization
# ---------------------------------------------------------------------------

def _resolve_csv_header(headers: list[str], field: str) -> str | None:
    """Find which actual CSV column maps to the canonical field name."""
    aliases = CSV_FIELD_ALIASES.get(field, [field])
    header_lower = {h.lower(): h for h in headers}
    for alias in aliases:
        if alias.lower() in header_lower:
            return header_lower[alias.lower()]
    return None


def _build_csv_header_map(headers: list[str]) -> dict[str, str]:
    """Build mapping from canonical field → actual CSV column name."""
    mapping = {}
    for field in CSV_FIELD_ALIASES:
        col = _resolve_csv_header(headers, field)
        if col:
            mapping[field] = col
    return mapping


def _normalize_csv_row(row: dict, header_map: dict, area_label: str | None, idx: int) -> dict | None:
    """Normalize a CSV row. Returns None if required fields are missing."""
    def get(field):
        col = header_map.get(field)
        return row.get(col, "").strip() if col else ""

    place_id = get("place_id")
    name = get("name")

    # Drop if missing both place_id and name
    if not place_id and not name:
        return None

    # Attempt numeric coercions
    def to_float(v):
        try:
            return float(v) if v else None
        except (ValueError, TypeError):
            return None

    def to_int(v):
        try:
            return int(float(v)) if v else None
        except (ValueError, TypeError):
            return None

    rating = to_float(get("rating"))
    review_count = to_int(get("review_count"))

    lat = to_float(get("lat"))
    lng = to_float(get("lng"))

    tags_raw = get("tags")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

    effective_area = area_label or get("area_label") or "Unknown"
    summary = get("summary") or (f"{name} in {effective_area}" if name else f"Place in {effective_area}")

    return {
        "place_id": place_id or None,
        "name": name or None,
        "primary_category": get("primary_category") or None,
        "area_label": area_label or get("area_label") or None,
        "rating": rating,
        "review_count": review_count,
        "price_level": get("price_level") or None,
        "formatted_address": get("formatted_address") or None,
        "lat": lat,
        "lng": lng,
        "tags": tags,
        "summary": summary,
        "source_fetched_at": _now_iso(),
    }


def normalize_csv(path: Path, area_label: str | None) -> tuple[list, list, list]:
    places = []
    warnings = []
    dropped = []

    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        header_map = _build_csv_header_map(headers)

        for i, row in enumerate(reader):
            result = _normalize_csv_row(row, header_map, area_label, i)
            if result is None:
                dropped.append(f"Dropped row[{i}]: missing place_id and name")
            else:
                places.append(result)

    return places, warnings, dropped


# ---------------------------------------------------------------------------
# User JSON normalization (flat list)
# ---------------------------------------------------------------------------

def _resolve_json_field(record: dict, field: str):
    """Find field value using alias matching (case-insensitive)."""
    aliases = JSON_FIELD_ALIASES.get(field, [field])
    record_lower = {k.lower(): v for k, v in record.items()}
    for alias in aliases:
        if alias.lower() in record_lower:
            return record_lower[alias.lower()]
    return None


def _normalize_json_record(record: dict, area_label: str | None, idx: int) -> dict | None:
    """Normalize a user-provided JSON record."""
    place_id = _resolve_json_field(record, "place_id")
    name = _resolve_json_field(record, "name")

    if not place_id and not name:
        return None

    def to_float(v):
        try:
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    def to_int(v):
        try:
            return int(float(v)) if v is not None else None
        except (ValueError, TypeError):
            return None

    rating = to_float(_resolve_json_field(record, "rating"))
    review_count = to_int(_resolve_json_field(record, "review_count"))
    lat = to_float(_resolve_json_field(record, "lat"))
    lng = to_float(_resolve_json_field(record, "lng"))

    tags_raw = _resolve_json_field(record, "tags")
    if isinstance(tags_raw, list):
        tags = tags_raw
    elif isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    else:
        tags = []

    area = area_label or _resolve_json_field(record, "area_label") or "Unknown"
    summary_raw = _resolve_json_field(record, "summary")
    summary = summary_raw or (f"{name} in {area}" if name else f"Place in {area}")

    price_level_raw = _resolve_json_field(record, "price_level")
    # Handle Google-style price levels if present in JSON
    price_level = GOOGLE_PRICE_MAP.get(str(price_level_raw), price_level_raw) if price_level_raw else None

    return {
        "place_id": place_id,
        "name": name,
        "primary_category": _resolve_json_field(record, "primary_category"),
        "area_label": area_label or _resolve_json_field(record, "area_label"),
        "rating": rating,
        "review_count": review_count,
        "price_level": price_level,
        "formatted_address": _resolve_json_field(record, "formatted_address"),
        "lat": lat,
        "lng": lng,
        "tags": tags,
        "summary": summary,
        "source_fetched_at": _now_iso(),
    }


def normalize_json(data, area_label: str | None) -> tuple[list, list, list]:
    places = []
    warnings = []
    dropped = []

    if isinstance(data, dict):
        # Wrap single object in list
        records = [data]
    elif isinstance(data, list):
        records = data
    else:
        return places, warnings, [f"Unexpected JSON structure: {type(data)}"]

    for i, record in enumerate(records):
        if not isinstance(record, dict):
            dropped.append(f"Dropped record[{i}]: not a JSON object")
            continue
        result = _normalize_json_record(record, area_label, i)
        if result is None:
            dropped.append(f"Dropped record[{i}]: missing place_id and name")
        else:
            places.append(result)

    return places, warnings, dropped


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Normalize place data into the internal schema.")
    parser.add_argument("--input", required=True, help="Path to input file")
    parser.add_argument("--source", choices=["google", "csv", "json"], help="Source format (auto-detected if omitted)")
    parser.add_argument("--area-label", default=None, help="Area label to apply to all records")
    parser.add_argument("--output", default=None, help="Write JSON output to this file (also prints to stdout)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        result = {"status": "error", "message": f"Input file not found: {input_path}"}
        print(json.dumps(result))
        sys.exit(1)

    # Load data (skip for CSV which streams)
    source = args.source
    data = None
    if source != "csv":
        try:
            with open(input_path, encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as e:
            # Might be CSV with no --source; try CSV fallback
            source = "csv"

    # Auto-detect source if not specified
    if source is None:
        source = detect_source(input_path, data)

    # Normalize
    if source == "google":
        if not isinstance(data, dict):
            data = {}
        places, warnings, dropped = normalize_google(data, args.area_label)
    elif source == "csv":
        places, warnings, dropped = normalize_csv(input_path, args.area_label)
    else:  # json
        places, warnings, dropped = normalize_json(data, args.area_label)

    total_input = len(places) + len(dropped)
    total_normalized = len(places)
    total_dropped = len(dropped)

    output = {
        "status": "ok",
        "places": places,
        "normalization_warnings": warnings + dropped,
        "total_input": total_input,
        "total_normalized": total_normalized,
        "total_dropped": total_dropped,
    }

    # Add partial failure warning when some records normalize and some are dropped
    if total_normalized > 0 and total_dropped > 0:
        output["warning"] = "normalization_partial_failure"

    # Use ensure_ascii=True for stdout (Windows cp1252 safe), full Unicode for file
    stdout_str = json.dumps(output, ensure_ascii=True, indent=2)
    sys.stdout.buffer.write(stdout_str.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
