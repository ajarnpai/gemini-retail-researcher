"""Tests for scripts/coordinate_parser.py."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_parser(*args):
    env = os.environ.copy()
    env["RTS_SKIP_ENV_FILE"] = "1"
    result = subprocess.run(
        [PYTHON, "scripts/coordinate_parser.py", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    return json.loads(result.stdout), result.returncode


class TestExplicitCoordinates:
    def test_explicit_lat_lng(self):
        out, code = run_parser("--lat", "40.7412", "--lng", "-73.9896")
        assert code == 0
        assert out["status"] == "ok"
        assert abs(out["lat"] - 40.7412) < 0.0001
        assert abs(out["lng"] + 73.9896) < 0.0001
        assert out["input_type"] == "explicit"

    def test_explicit_out_of_range_lat(self):
        out, code = run_parser("--lat", "95.0", "--lng", "-73.0")
        assert code == 1
        assert out["status"] == "error"
        assert out["error_code"] == "invalid_location_input"


class TestCoordinateString:
    def test_comma_separated(self):
        out, code = run_parser("--input", "40.7412, -73.9896")
        assert code == 0
        assert out["status"] == "ok"
        assert out["input_type"] == "coordinate_string"
        assert abs(out["lat"] - 40.7412) < 0.0001

    def test_garbage_input(self):
        out, code = run_parser("--input", "not a coordinate")
        assert code == 1
        assert out["error_code"] == "invalid_location_input"


class TestGoogleMapsURL:
    def test_at_sign_format(self):
        url = "https://www.google.com/maps/@40.7412,-73.9896,15z"
        out, code = run_parser("--input", url)
        assert code == 0
        assert out["input_type"] == "google_maps_url"
        assert abs(out["lat"] - 40.7412) < 0.0001

    def test_query_format(self):
        url = "https://www.google.com/maps?q=40.7412,-73.9896"
        out, code = run_parser("--input", url)
        assert code == 0
        assert out["input_type"] == "google_maps_url"

    def test_maps_app_shortlink(self):
        url = "https://maps.app.goo.gl/hQojk3uAvhQj2EGJA"
        out, code = run_parser("--input", url)
        assert code == 0
        assert out["input_type"] == "google_maps_url"
        assert abs(out["lat"] - 13.7227798) < 0.0001
        assert abs(out["lng"] - 100.5408628) < 0.0001
