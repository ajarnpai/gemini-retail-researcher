"""Tests for scripts/places_details.py."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_details(*args, env_override=None):
    env = os.environ.copy()
    env.pop("GOOGLE_PLACES_API_KEY", None)
    env["RTS_SKIP_ENV_FILE"] = "1"
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        [PYTHON, "scripts/places_details.py", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    try:
        return json.loads(result.stdout), result.returncode
    except json.JSONDecodeError:
        return {"raw": result.stdout, "stderr": result.stderr}, result.returncode


class TestValidation:
    def test_no_api_key(self):
        out, code = run_details("--place-ids", "ChIJ_test")
        assert code == 1
        assert out["error_code"] == "no_api_key"

    def test_too_many_ids(self):
        ids = [f"ChIJ_{i}" for i in range(11)]
        out, code = run_details("--place-ids", *ids, env_override={"GOOGLE_PLACES_API_KEY": "fake_key"})
        assert code == 1
        assert out["error_code"] == "invalid_query"
        assert "10" in out["message"]
