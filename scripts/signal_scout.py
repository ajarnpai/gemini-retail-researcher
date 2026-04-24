"""Signal Scout Orchestrator: Unified market intelligence gathering."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path to allow imports from scripts.*
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from scripts.config import OUTPUT_DIR
from scripts.workers.trends_worker import fetch_trends
from scripts.workers.youtube_worker import fetch_youtube_signals
from scripts.core.normalizer import normalize_signal
from scripts.core.linker import link_signals


def _error(code: str, message: str) -> None:
    payload = {"status": "error", "error_code": code, "message": message}
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.exit(1)


def _run_json(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True)
    if not result.stdout.strip():
        # Check stderr for possible error messages
        stderr = result.stderr.strip()
        raise RuntimeError(f"Command produced no stdout: {' '.join(command)}\nSTDERR: {stderr}")
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
    return "-".join(parts) or "signal-scout"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description="Signal Scout Orchestrator")
    parser.add_argument("--input", help="Coordinates, Google Maps URL, or alias")
    parser.add_argument("--keyword", action="append", help="Keyword for Trends and YouTube")
    parser.add_argument("--category", action="append", help="Google Places category")
    parser.add_argument("--radius", type=float, default=1.5, help="Search radius in km")
    parser.add_argument("--max-results", type=int, default=60, help="Max results per category (API cap is 60)")
    parser.add_argument("--session-name", default=None, help="Optional session name")
    args = parser.parse_args()

    if not args.input:
        _error("invalid_query", "--input is required")
    if not args.keyword:
        _error("invalid_query", "At least one --keyword is required")
    if not args.category:
        _error("invalid_query", "At least one --category is required")

    session_name = args.session_name or f"{_slugify(args.input)}-{_slugify(args.keyword[0])}"
    session_dir = Path(OUTPUT_DIR) / "raw" / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parse location
    try:
        location_data = _run_json([
            sys.executable, str(SCRIPT_DIR / "coordinate_parser.py"),
            "--input", args.input
        ])
    except Exception as e:
        _error("location_error", str(e))

    lat = location_data["lat"]
    lng = location_data["lng"]

    signals = []
    raw_results = {
        "google_trends": [],
        "youtube": [],
        "google_places": []
    }
    worker_status = {
        "google_trends": "ok",
        "youtube": "ok",
        "google_places": "ok"
    }
    overall_status = "ok"

    # 2. Google Trends
    try:
        # pytrends limit is 5 keywords per request
        for i in range(0, len(args.keyword), 5):
            batch = args.keyword[i:i+5]
            trends_res = fetch_trends(batch)
            if trends_res["status"] == "ok":
                raw_results["google_trends"].append(trends_res)
                # Normalize each keyword
                for kw in batch:
                    if kw in trends_res.get("current_values", {}):
                        raw_kw_data = {
                            "geo": trends_res.get("geo"),
                            "keyword": kw,
                            "current_value": trends_res["current_values"][kw],
                            "peak": trends_res.get("peaks", {}).get(kw)
                        }
                        signals.append(normalize_signal(raw_kw_data, "google_trends"))
            else:
                worker_status["google_trends"] = f"error: {trends_res.get('message', 'unknown error')}"
                overall_status = "partial_success"
    except Exception as e:
        worker_status["google_trends"] = f"error: {str(e)}"
        overall_status = "partial_success"

    # 3. YouTube
    try:
        for kw in args.keyword:
            yt_res = fetch_youtube_signals(kw)
            if yt_res["status"] == "ok":
                raw_results["youtube"].append(yt_res)
                for video in yt_res.get("videos", []):
                    signals.append(normalize_signal(video, "youtube"))
            else:
                worker_status["youtube"] = f"error: {yt_res.get('message', 'unknown error')}"
                overall_status = "partial_success"
    except Exception as e:
        worker_status["youtube"] = f"error: {str(e)}"
        overall_status = "partial_success"

    # 4. Google Places
    for cat in args.category:
        try:
            places_res = _run_json([
                sys.executable, str(SCRIPT_DIR / "places_search.py"),
                "--lat", str(lat),
                "--lng", str(lng),
                "--radius", str(args.radius),
                "--category", cat,
                "--max-results", str(args.max_results)
            ])
            if places_res["status"] == "ok":
                raw_results["google_places"].append(places_res)
                for place in places_res.get("results", []):
                    # We might need to pass area_label but it's not required by normalizer yet
                    signals.append(normalize_signal(place, "google_places"))
            else:
                worker_status["google_places"] = f"error: {places_res.get('message', 'unknown error')}"
                overall_status = "partial_success"
        except Exception as e:
            worker_status["google_places"] = f"error: {str(e)}"
            overall_status = "partial_success"
            print(f"Warning: Places search failed for category {cat}: {e}", file=sys.stderr)

    # 5. Link signals
    signals = link_signals(signals)

    # 6. Save outputs
    dump_path = session_dir / "signal_dump.json"
    dump_path.write_text(json.dumps({
        "status": overall_status,
        "worker_status": worker_status,
        "session_name": session_name,
        "fetched_at": _now_iso(),
        "query": {
            "input": args.input,
            "lat": lat,
            "lng": lng,
            "keywords": args.keyword,
            "categories": args.category,
            "radius": args.radius
        },
        "signals": signals,
        "raw": raw_results
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest = {
        "status": overall_status,
        "worker_status": worker_status,
        "session_name": session_name,
        "generated_at": _now_iso(),
        "files": [
            {"name": "signal_dump.json", "path": str(dump_path)}
        ]
    }
    manifest_path = session_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # 6. Output summary to stdout
    summary = {
        "status": overall_status,
        "worker_status": worker_status,
        "session_name": session_name,
        "output_dir": str(session_dir),
        "counts": {
            "total_signals": len(signals),
            "trends": sum(len(r.get("current_values", {})) for r in raw_results["google_trends"]),
            "youtube_videos": sum(len(r.get("videos", [])) for r in raw_results["youtube"]),
            "places": sum(len(r.get("results", [])) for r in raw_results["google_places"])
        },
        "manifest": manifest
    }
    sys.stdout.buffer.write(json.dumps(summary, indent=2, ensure_ascii=True).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
