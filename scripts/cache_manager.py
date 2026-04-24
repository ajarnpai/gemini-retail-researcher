"""File-based JSON cache with TTL.

CLI: python scripts/cache_manager.py --action get|set|clear|stats --key <key> [--value <json>] [--ttl <seconds>]

Cache files stored at: cache/{sha256_hash_16chars}.json
Each file contains: {"key": str, "data": any, "created_at": float, "ttl_seconds": int}
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from config import CACHE_DIR


def _cache_path(key: str, cache_dir: str) -> Path:
    h = hashlib.sha256(key.encode()).hexdigest()[:16]
    return Path(cache_dir) / f"{h}.json"


def _ensure_dir(cache_dir: str):
    Path(cache_dir).mkdir(parents=True, exist_ok=True)


def cache_get(key: str, cache_dir: str) -> dict:
    path = _cache_path(key, cache_dir)
    if not path.exists():
        return {"status": "ok", "cache_status": "miss", "data": None}
    with open(path) as f:
        entry = json.load(f)
    if entry.get("key") != key:
        return {"status": "ok", "cache_status": "miss", "data": None}
    age = time.time() - entry["created_at"]
    if age <= entry["ttl_seconds"]:
        return {"status": "ok", "cache_status": "hit", "data": entry["data"]}
    else:
        return {"status": "ok", "cache_status": "stale", "data": entry["data"]}


def cache_set(key: str, value: str, ttl: int, cache_dir: str) -> dict:
    _ensure_dir(cache_dir)
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error_code": "invalid_query",
            "message": f"Invalid JSON value: {exc}",
        }
    entry = {"key": key, "data": data, "created_at": time.time(), "ttl_seconds": ttl}
    path = _cache_path(key, cache_dir)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(entry, f)
    tmp_path.replace(path)
    return {"status": "ok", "action": "set", "key": key}


def cache_clear(cache_dir: str) -> dict:
    d = Path(cache_dir)
    count = 0
    if d.exists():
        for f in d.glob("*.json"):
            f.unlink()
            count += 1
    return {"status": "ok", "action": "clear", "removed": count}


def cache_stats(cache_dir: str) -> dict:
    d = Path(cache_dir)
    total = fresh = stale = 0
    now = time.time()
    if d.exists():
        for f in d.glob("*.json"):
            try:
                with open(f) as fh:
                    entry = json.load(fh)
                total += 1
                if now - entry["created_at"] <= entry["ttl_seconds"]:
                    fresh += 1
                else:
                    stale += 1
            except (json.JSONDecodeError, KeyError):
                total += 1
                stale += 1
    return {"status": "ok", "total_entries": total, "fresh": fresh, "stale": stale}


def main():
    parser = argparse.ArgumentParser(description="File-based JSON cache")
    parser.add_argument("--action", required=True, choices=["get", "set", "clear", "stats"])
    parser.add_argument("--key", type=str)
    parser.add_argument("--value", type=str)
    parser.add_argument("--value-file", type=str, dest="value_file", help="Read value from file instead of --value")
    parser.add_argument("--ttl", type=int, default=3600)
    args = parser.parse_args()

    cache_dir = os.environ.get("RTS_CACHE_DIR", CACHE_DIR)

    if args.action == "get":
        if not args.key:
            print(json.dumps({"status": "error", "error_code": "invalid_query", "message": "--key required for get"}))
            sys.exit(1)
        result = cache_get(args.key, cache_dir)
    elif args.action == "set":
        # Support --value-file as alternative to --value (avoids command-line length limits)
        value = args.value
        if not value and args.value_file:
            with open(args.value_file) as f:
                value = f.read()
        if not args.key or not value:
            print(json.dumps({"status": "error", "error_code": "invalid_query", "message": "--key and --value (or --value-file) required for set"}))
            sys.exit(1)
        result = cache_set(args.key, value, args.ttl, cache_dir)
        if result.get("status") == "error":
            print(json.dumps(result))
            sys.exit(1)
    elif args.action == "clear":
        result = cache_clear(cache_dir)
    elif args.action == "stats":
        result = cache_stats(cache_dir)

    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
