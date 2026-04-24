"""Tests for scripts/retail_research.py."""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
TMP_ROOT = ROOT / "data" / "_test_tmp"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


def run_research(*args):
    env = os.environ.copy()
    env["RTS_SKIP_ENV_FILE"] = "1"
    result = subprocess.run(
        [PYTHON, "scripts/retail_research.py", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    if not result.stdout.strip():
        raise AssertionError(f"No stdout from retail_research.py\nSTDERR:\n{result.stderr}")
    return json.loads(result.stdout), result.returncode


def write_json(data):
    path = TMP_ROOT / f"input-{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_temp_dir() -> str:
    path = TMP_ROOT / f"session-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def test_offline_session_writes_bundle():
    input_path = write_json(
        [
            {
                "place_id": "a1",
                "name": "North Plaza",
                "category": "shopping_mall",
                "rating": 4.3,
                "review_count": 220,
                "price_level": "mid",
                "formatted_address": "1 Main St",
                "lat": 40.7412,
                "lng": -73.9896,
                "tags": ["shopping_mall", "store"],
            },
            {
                "place_id": "a2",
                "name": "North Plaza",
                "category": "shopping_mall",
                "rating": 4.0,
                "review_count": 120,
                "formatted_address": "2 Main St",
                "lat": 40.7420,
                "lng": -73.9880,
                "tags": ["shopping_mall", "store"],
            },
            {
                "place_id": "b1",
                "name": "Corner Shoes",
                "category": "shoe_store",
                "rating": 4.6,
                "review_count": 80,
                "formatted_address": "3 Main St",
                "lat": 40.7400,
                "lng": -73.9900,
                "tags": ["shoe_store", "store"],
            },
        ]
    )
    output_root = make_temp_dir()
    try:
        out, code = run_research(
            "--input-file",
            str(input_path),
            "--source",
            "json",
            "--session-name",
            "offline-bundle",
            "--output-root",
            output_root,
        )
        assert code == 0
        output_dir = Path(out["output_dir"])
        assert (output_dir / "raw_search.json").exists()
        assert (output_dir / "normalized_places.json").exists()
        assert (output_dir / "market_summary.json").exists()
        assert (output_dir / "research_brief.md").exists()
        assert (output_dir / "manifest.json").exists()

        summary = json.loads((output_dir / "market_summary.json").read_text(encoding="utf-8"))
        assert summary["total_places"] == 3
        assert summary["repeated_brands"][0]["brand"] == "north plaza"
        assert summary["primary_category_frequency"]["shopping_mall"] == 2

        brief = (output_dir / "research_brief.md").read_text(encoding="utf-8")
        assert "## Research Target" in brief
        assert "## Market Overview" in brief
    finally:
        shutil.rmtree(output_root, ignore_errors=True)
        input_path.unlink(missing_ok=True)


def test_offline_sparse_session_still_writes_bundle():
    input_path = write_json([])
    output_root = make_temp_dir()
    try:
        out, code = run_research(
            "--input-file",
            str(input_path),
            "--source",
            "json",
            "--session-name",
            "empty-bundle",
            "--output-root",
            output_root,
        )
        assert code == 0
        output_dir = Path(out["output_dir"])
        summary = json.loads((output_dir / "market_summary.json").read_text(encoding="utf-8"))
        assert summary["total_places"] == 0
        assert summary["follow_up_questions"]
    finally:
        shutil.rmtree(output_root, ignore_errors=True)
        input_path.unlink(missing_ok=True)
