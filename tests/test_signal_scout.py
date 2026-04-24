"""Basic integration test for Signal Scout Orchestrator."""

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

# Add project root and scripts directory to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

from scripts.signal_scout import main


def test_signal_scout_basic_flow():
    """Verify that the orchestrator runs and creates output files."""
    session_name = "test-integration-session"
    output_dir = ROOT / "output" / "raw" / session_name
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # Mock CLI arguments
    test_args = [
        "signal_scout.py",
        "--input", "40.7412,-73.9896",
        "--keyword", "coffee",
        "--category", "cafe",
        "--session-name", session_name
    ]

    # Mock _run_json for coordinate_parser and places_search
    mock_responses = [
        {"status": "ok", "lat": 40.7412, "lng": -73.9896},  # coordinate_parser
        {
            "status": "ok",
            "results": [
                {
                    "name": "Test Cafe",
                    "place_id": "place_123",
                    "rating": 4.5,
                    "location": {"latitude": 40.7412, "longitude": -73.9896},
                    "types": ["cafe"]
                }
            ]
        }  # places_search
    ]

    # Mock workers and internal helpers
    with patch("sys.argv", test_args), \
         patch("scripts.signal_scout._run_json") as mock_run_json, \
         patch("scripts.signal_scout.fetch_trends") as mock_fetch_trends, \
         patch("scripts.signal_scout.fetch_youtube_signals") as mock_fetch_youtube:

        mock_run_json.side_effect = mock_responses
        
        mock_fetch_trends.return_value = {
            "status": "ok",
            "geo": "TH",
            "current_values": {"coffee": {"value": 80, "direction": "rising"}},
            "peaks": {"coffee": {"value": 100, "date": "2023-01-01"}}
        }
        
        mock_fetch_youtube.return_value = {
            "status": "ok",
            "videos": [
                {
                    "video_id": "vid_123",
                    "title": "Coffee in Bangkok",
                    "view_count": 1000,
                    "like_count": 100,
                    "comment_count": 10,
                    "published_at": "2023-01-01T00:00:00Z",
                    "detected_areas": ["sukhumvit"],
                    "detected_categories": ["cafe_bakery"]
                }
            ]
        }

        # Redirect stdout to avoid cluttering test output
        with patch("sys.stdout.buffer.write"):
            main()

    # Assertions
    assert output_dir.exists(), f"Output directory {output_dir} was not created"
    
    dump_path = output_dir / "signal_dump.json"
    assert dump_path.exists(), "signal_dump.json was not created"
    
    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists(), "manifest.json was not created"

    with open(dump_path, encoding="utf-8") as f:
        data = json.load(f)
        assert data["status"] == "ok"
        assert data["session_name"] == session_name
        assert len(data["signals"]) >= 3  # trends, youtube, places
        
        sources = {s["source"] for s in data["signals"]}
        assert "google_trends" in sources
        assert "youtube" in sources
        assert "google_places" in sources

    # Cleanup
    shutil.rmtree(output_dir)


def test_signal_scout_partial_success():
    """Verify that the orchestrator handles worker failures gracefully."""
    session_name = "test-partial-session"
    output_dir = ROOT / "output" / "raw" / session_name
    if output_dir.exists():
        shutil.rmtree(output_dir)

    test_args = [
        "signal_scout.py",
        "--input", "40.7412,-73.9896",
        "--keyword", "coffee",
        "--category", "cafe",
        "--session-name", session_name
    ]

    mock_responses = [
        {"status": "ok", "lat": 40.7412, "lng": -73.9896},  # coordinate_parser
        {
            "status": "ok",
            "results": [
                {"name": "Test Cafe", "place_id": "p1", "rating": 4.5}
            ]
        }  # places_search
    ]

    with patch("sys.argv", test_args), \
         patch("scripts.signal_scout._run_json") as mock_run_json, \
         patch("scripts.signal_scout.fetch_trends") as mock_fetch_trends, \
         patch("scripts.signal_scout.fetch_youtube_signals") as mock_fetch_youtube:

        mock_run_json.side_effect = mock_responses
        
        # Trends fails
        mock_fetch_trends.return_value = {"status": "error", "message": "Quota exceeded"}
        
        # YouTube succeeds
        mock_fetch_youtube.return_value = {
            "status": "ok",
            "videos": [{"video_id": "v1", "title": "Vid"}]
        }

        with patch("sys.stdout.buffer.write"):
            main()

    # Assertions
    assert output_dir.exists()
    dump_path = output_dir / "signal_dump.json"
    with open(dump_path, encoding="utf-8") as f:
        data = json.load(f)
        assert data["status"] == "partial_success"
        assert data["worker_status"]["google_trends"] == "error: Quota exceeded"
        assert data["worker_status"]["youtube"] == "ok"
        assert data["worker_status"]["google_places"] == "ok"
        
        # Should still have youtube and places signals
        sources = {s["source"] for s in data["signals"]}
        assert "youtube" in sources
        assert "google_places" in sources
        assert "google_trends" not in sources

    # Cleanup
    shutil.rmtree(output_dir)


if __name__ == "__main__":
    # Allow running the test directly
    try:
        test_signal_scout_basic_flow()
        print("Test passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
