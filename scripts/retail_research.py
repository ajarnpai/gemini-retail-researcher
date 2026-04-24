"""Run a lightweight retail research session and write a handoff bundle."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from config import OUTPUT_DIR

SCRIPT_DIR = Path(__file__).resolve().parent


def _error(code: str, message: str) -> None:
    payload = {"status": "error", "error_code": code, "message": message}
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.exit(1)


def _run_json(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True)
    if not result.stdout.strip():
        raise RuntimeError(f"Command produced no stdout: {' '.join(command)}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Command returned invalid JSON: {' '.join(command)}\nSTDERR: {result.stderr}"
        ) from exc
    if result.returncode != 0:
        message = payload.get("message", f"Command failed: {' '.join(command)}")
        raise RuntimeError(message)
    return payload


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts) or "retail-research"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_raw_places(places: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for place in places:
        key = place.get("id") or json.dumps(place, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(place)
    return unique


def _load_json(path: Path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def _brand_key(name: str | None) -> str | None:
    if not name:
        return None
    trimmed = name.split(" - ")[0].split(" | ")[0].split("(")[0].strip().lower()
    normalized = " ".join(part for part in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in trimmed).split())
    return normalized or None


def _summarize_places(places: list[dict], query: dict, warnings: list[str]) -> dict:
    ratings = [place["rating"] for place in places if isinstance(place.get("rating"), (int, float))]
    review_counts = [place["review_count"] for place in places if isinstance(place.get("review_count"), int)]
    price_counts = Counter(place.get("price_level") for place in places if place.get("price_level"))
    category_counts = Counter(place.get("primary_category") for place in places if place.get("primary_category"))
    tag_counts = Counter(tag for place in places for tag in place.get("tags", []))
    brand_counts = Counter(key for key in (_brand_key(place.get("name")) for place in places) if key)

    repeated_brands = [
        {"brand": brand, "location_count": count}
        for brand, count in brand_counts.most_common()
        if count > 1
    ]

    notable_competitors = sorted(
        places,
        key=lambda place: (
            place.get("review_count") or -1,
            place.get("rating") or -1,
            place.get("name") or "",
        ),
        reverse=True,
    )[:10]

    follow_up_questions = []
    if len(places) <= 3:
        follow_up_questions.append("Broaden the radius or add adjacent retail categories to confirm market depth.")
    if not repeated_brands:
        follow_up_questions.append("Check whether nearby adjacent blocks reveal brand clusters not visible in this scan.")
    if len(category_counts) <= 2:
        follow_up_questions.append("Run one more scan with adjacent Google Places categories to widen the competitive set.")

    return {
        "status": "ok",
        "generated_at": _now_iso(),
        "query": query,
        "total_places": len(places),
        "average_rating": round(statistics.mean(ratings), 2) if ratings else None,
        "median_review_count": statistics.median(review_counts) if review_counts else None,
        "price_level_distribution": dict(sorted(price_counts.items())),
        "primary_category_frequency": dict(category_counts.most_common()),
        "top_tags": [{"tag": tag, "count": count} for tag, count in tag_counts.most_common(15)],
        "repeated_brands": repeated_brands,
        "notable_competitors": [
            {
                "name": place.get("name"),
                "primary_category": place.get("primary_category"),
                "rating": place.get("rating"),
                "review_count": place.get("review_count"),
                "price_level": place.get("price_level"),
                "formatted_address": place.get("formatted_address"),
                "summary": place.get("summary"),
            }
            for place in notable_competitors
        ],
        "warnings": warnings,
        "follow_up_questions": follow_up_questions,
    }


def _build_brief(summary: dict, manifest: dict) -> str:
    query = summary["query"]
    lines = [
        f"# Research Brief: {query['session_name']}",
        "",
        "## Research Target",
        f"- Session: {query['session_name']}",
        f"- Mode: {query['mode']}",
        f"- Categories: {', '.join(query.get('categories', [])) or 'n/a'}",
    ]
    if query.get("location_input"):
        lines.append(f"- Location input: {query['location_input']}")
    if query.get("center"):
        lines.append(f"- Center: {query['center']['lat']}, {query['center']['lng']}")
    if query.get("radius_km") is not None:
        lines.append(f"- Radius: {query['radius_km']} km")
    if query.get("price_tier"):
        lines.append(f"- Price tier: {query['price_tier']}")

    lines.extend(
        [
            "",
            "## Source and Provenance",
            f"- Generated at: {summary['generated_at']}",
            f"- Files: {', '.join(file_info['name'] for file_info in manifest['files'])}",
            "",
            "## Market Overview",
            f"- Total places: {summary['total_places']}",
            f"- Average rating: {summary['average_rating'] if summary['average_rating'] is not None else 'n/a'}",
            f"- Median review count: {summary['median_review_count'] if summary['median_review_count'] is not None else 'n/a'}",
            "",
            "## Notable Competitors and Repeated Brands",
        ]
    )

    if summary["repeated_brands"]:
        for brand in summary["repeated_brands"][:10]:
            lines.append(f"- Repeated brand: {brand['brand']} ({brand['location_count']} listings)")
    else:
        lines.append("- No repeated brand names detected in this scan.")

    for competitor in summary["notable_competitors"][:5]:
        lines.append(
            f"- {competitor['name']} | {competitor.get('primary_category') or 'unknown category'} | "
            f"rating {competitor.get('rating') or 'n/a'} | reviews {competitor.get('review_count') or 'n/a'}"
        )

    lines.extend(["", "## Category and Pricing Patterns"])
    if summary["primary_category_frequency"]:
        for category, count in list(summary["primary_category_frequency"].items())[:10]:
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- No primary categories were available in normalized data.")

    if summary["price_level_distribution"]:
        lines.append(f"- Price levels: {json.dumps(summary['price_level_distribution'], ensure_ascii=False)}")
    else:
        lines.append("- Price level data was sparse or unavailable.")

    lines.extend(["", "## Gaps, Ambiguities, and Follow-up Questions"])
    if summary["warnings"]:
        for warning in summary["warnings"]:
            lines.append(f"- Warning: {warning}")
    for question in summary["follow_up_questions"]:
        lines.append(f"- {question}")

    lines.extend(
        [
            "",
            "## Recommended Next Prompts",
            "- Identify the strongest competitor clusters and the likely trade area boundaries.",
            "- Compare the visible brand mix with adjacent categories that may compete for the same shopper.",
            "- Propose follow-up searches that would reduce ambiguity in pricing, anchors, or brand presence.",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run a lightweight retail research session.")
    parser.add_argument("--input", dest="location_input", help="Coordinates, Google Maps URL, or configured alias")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lng", type=float, help="Longitude")
    parser.add_argument("--radius", type=float, help="Radius in km for live searches")
    parser.add_argument("--category", action="append", dest="categories", help="Google Places includedType; repeat for multiple categories")
    parser.add_argument("--price-tier", default=None, help="Optional price tier filter")
    parser.add_argument("--max-results", type=int, default=60, help="Max results per category (API cap is 60)")
    parser.add_argument("--input-file", default=None, help="Optional local CSV or JSON file for offline mode")
    parser.add_argument("--source", choices=["google", "csv", "json"], default=None, help="Input file source type in offline mode")
    parser.add_argument("--session-name", default=None, help="Optional session directory name")
    parser.add_argument("--output-root", default=str(Path(OUTPUT_DIR) / "raw"), help="Root directory for session outputs")
    args = parser.parse_args()

    live_mode = args.input_file is None
    if live_mode:
        if not args.categories:
            _error("invalid_query", "Live mode requires at least one --category.")
        if args.radius is None:
            _error("invalid_query", "Live mode requires --radius.")
        if not ((args.lat is not None and args.lng is not None) or args.location_input):
            _error("invalid_query", "Live mode requires --input or both --lat and --lng.")
    else:
        if args.location_input or args.lat is not None or args.lng is not None or args.radius is not None or args.categories:
            # Keep offline usage explicit to avoid mixed-mode ambiguity.
            _error("invalid_query", "Offline mode uses --input-file and optional --source only.")

    session_name = args.session_name
    if not session_name:
        if live_mode:
            base = args.location_input or f"{args.lat},{args.lng}"
            session_name = f"{_slugify(base)}-{_slugify('-'.join(args.categories or []))}"
        else:
            session_name = _slugify(Path(args.input_file).stem)

    session_dir = Path(args.output_root) / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    raw_path = session_dir / "raw_search.json"
    normalized_path = session_dir / "normalized_places.json"
    summary_path = session_dir / "market_summary.json"
    brief_path = session_dir / "research_brief.md"
    manifest_path = session_dir / "manifest.json"

    warnings: list[str] = []
    query: dict = {"session_name": session_name, "mode": "live" if live_mode else "offline"}

    if live_mode:
        if args.location_input:
            parsed = _run_json(
                [sys.executable, str(SCRIPT_DIR / "coordinate_parser.py"), "--input", args.location_input]
            )
            center_lat = parsed["lat"]
            center_lng = parsed["lng"]
            query["location_input"] = args.location_input
        else:
            parsed = _run_json(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "coordinate_parser.py"),
                    "--lat",
                    str(args.lat),
                    "--lng",
                    str(args.lng),
                ]
            )
            center_lat = parsed["lat"]
            center_lng = parsed["lng"]

        raw_searches = []
        raw_places: list[dict] = []
        for category in args.categories or []:
            command = [
                sys.executable,
                str(SCRIPT_DIR / "places_search.py"),
                "--lat",
                str(center_lat),
                "--lng",
                str(center_lng),
                "--radius",
                str(args.radius),
                "--category",
                category,
                "--max-results",
                str(args.max_results),
            ]
            if args.price_tier:
                command.extend(["--price-tier", args.price_tier])
            search_result = _run_json(command)
            if search_result.get("warning_message"):
                warnings.append(search_result["warning_message"])
            raw_searches.append(search_result)
            raw_places.extend(search_result.get("results", []))

        raw_payload = {
            "status": "ok",
            "mode": "live",
            "query": {
                "center": {"lat": center_lat, "lng": center_lng},
                "radius_km": args.radius,
                "categories": args.categories,
                "price_tier": args.price_tier,
                "location_input": args.location_input,
            },
            "searches": raw_searches,
            "results": _dedupe_raw_places(raw_places),
            "fetched_at": _now_iso(),
        }
        raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        normalize_command = [
            sys.executable,
            str(SCRIPT_DIR / "places_normalize.py"),
            "--input",
            str(raw_path),
            "--source",
            "google",
            "--output",
            str(normalized_path),
        ]
        normalized_payload = _run_json(normalize_command)
        query.update(
            {
                "center": {"lat": center_lat, "lng": center_lng},
                "radius_km": args.radius,
                "categories": args.categories,
                "price_tier": args.price_tier,
                "location_input": args.location_input,
            }
        )
    else:
        input_path = Path(args.input_file)
        if not input_path.exists():
            _error("file_not_found", f"Input file not found: {input_path}")
        raw_data = _load_json(input_path) if input_path.suffix.lower() == ".json" else None
        raw_payload = {
            "status": "ok",
            "mode": "offline",
            "query": {"input_file": str(input_path), "source": args.source},
            "results": raw_data,
            "fetched_at": _now_iso(),
        }
        raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        normalize_command = [
            sys.executable,
            str(SCRIPT_DIR / "places_normalize.py"),
            "--input",
            str(input_path),
            "--output",
            str(normalized_path),
        ]
        if args.source:
            normalize_command.extend(["--source", args.source])
        normalized_payload = _run_json(normalize_command)
        query.update({"input_file": str(input_path), "source": args.source})

    normalized_places = normalized_payload.get("places", [])
    warnings.extend(normalized_payload.get("normalization_warnings", []))

    summary_payload = _summarize_places(normalized_places, query, warnings)
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "status": "ok",
        "session_name": session_name,
        "generated_at": _now_iso(),
        "query": query,
        "files": [
            {"name": "raw_search.json", "path": str(raw_path)},
            {"name": "normalized_places.json", "path": str(normalized_path)},
            {"name": "market_summary.json", "path": str(summary_path)},
            {"name": "research_brief.md", "path": str(brief_path)},
            {"name": "manifest.json", "path": str(manifest_path)},
        ],
    }

    brief_path.write_text(_build_brief(summary_payload, manifest), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    stdout_payload = {
        "status": "ok",
        "session_name": session_name,
        "output_dir": str(session_dir),
        "manifest": manifest,
    }
    sys.stdout.buffer.write(json.dumps(stdout_payload, ensure_ascii=True, indent=2).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
