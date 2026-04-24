"""Tests for scripts/places_search.py."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_search(*args, env_override=None):
    env = os.environ.copy()
    env.pop("GOOGLE_PLACES_API_KEY", None)
    env["RTS_SKIP_ENV_FILE"] = "1"
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        [PYTHON, "scripts/places_search.py", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    try:
        return json.loads(result.stdout), result.returncode
    except json.JSONDecodeError:
        return {"raw": result.stdout, "stderr": result.stderr}, result.returncode


class TestMissingApiKey:
    def test_no_api_key_returns_error(self):
        out, code = run_search(
            "--lat",
            "40.7412",
            "--lng",
            "-73.9896",
            "--radius",
            "1.5",
            "--category",
            "clothing_store",
        )
        assert code == 1
        assert out["error_code"] == "no_api_key"


class TestInputValidation:
    def test_radius_too_small(self):
        out, code = run_search(
            "--lat",
            "40.7412",
            "--lng",
            "-73.9896",
            "--radius",
            "0.1",
            "--category",
            "clothing_store",
            env_override={"GOOGLE_PLACES_API_KEY": "fake_key"},
        )
        assert code == 1
        assert out["error_code"] == "invalid_query"

    def test_radius_too_large(self):
        out, code = run_search(
            "--lat",
            "40.7412",
            "--lng",
            "-73.9896",
            "--radius",
            "50.0",
            "--category",
            "clothing_store",
            env_override={"GOOGLE_PLACES_API_KEY": "fake_key"},
        )
        assert code == 1
        assert out["error_code"] == "invalid_query"
