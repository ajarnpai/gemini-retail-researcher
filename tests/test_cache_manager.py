"""Tests for scripts/cache_manager.py."""

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
TMP_ROOT = ROOT / "data" / "_test_tmp"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


def run_cache(*args, cache_dir=None):
    env = os.environ.copy()
    env["RTS_SKIP_ENV_FILE"] = "1"
    if cache_dir:
        env["RTS_CACHE_DIR"] = cache_dir
    result = subprocess.run(
        [PYTHON, "scripts/cache_manager.py", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    return json.loads(result.stdout), result.returncode


def make_temp_dir() -> str:
    path = TMP_ROOT / f"cache-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


class TestCacheSetAndGet:
    def test_set_then_get_hit(self):
        cache_dir = make_temp_dir()
        value_file = Path(cache_dir) / "value.json"
        value_file.write_text('{"data": 1}', encoding="utf-8")
        try:
            run_cache("--action", "set", "--key", "test_key", "--value-file", str(value_file), "--ttl", "3600", cache_dir=cache_dir)
            out, code = run_cache("--action", "get", "--key", "test_key", cache_dir=cache_dir)
            assert code == 0
            assert out["status"] == "ok"
            assert out["cache_status"] == "hit"
            assert out["data"] == {"data": 1}
        finally:
            shutil.rmtree(cache_dir, ignore_errors=True)

    def test_expired_returns_stale(self):
        cache_dir = make_temp_dir()
        value_file = Path(cache_dir) / "value.json"
        value_file.write_text('{"x": 2}', encoding="utf-8")
        try:
            run_cache("--action", "set", "--key", "exp_key", "--value-file", str(value_file), "--ttl", "1", cache_dir=cache_dir)
            time.sleep(1.5)
            out, code = run_cache("--action", "get", "--key", "exp_key", cache_dir=cache_dir)
            assert code == 0
            assert out["cache_status"] == "stale"
            assert out["data"] == {"x": 2}
        finally:
            shutil.rmtree(cache_dir, ignore_errors=True)
