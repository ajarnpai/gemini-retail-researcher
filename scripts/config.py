"""Shared configuration for lightweight retail research scripts."""

import os
from pathlib import Path

# --- Directories ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = os.environ.get("RTS_CACHE_DIR", str(PROJECT_ROOT / "cache"))
OUTPUT_DIR = os.environ.get("RTS_OUTPUT_DIR", str(PROJECT_ROOT / "output"))
DATA_DIR = os.environ.get("RTS_DATA_DIR", str(PROJECT_ROOT / "data"))

# --- Load .env if present (secrets stay in memory, never logged) ---
_env_path = PROJECT_ROOT / ".env"
if os.environ.get("RTS_SKIP_ENV_FILE") != "1" and _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# --- API Keys (loaded from .env or environment) ---
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", GOOGLE_PLACES_API_KEY)

# --- Cache TTLs ---
SEARCH_CACHE_TTL_SECONDS = 3600
DETAILS_CACHE_TTL_SECONDS = 86400

# --- Search limits ---
MAX_RESULTS_DEFAULT = 60  # Google Places API standard max is 60 (3 pages)
MAX_PLACE_IDS_PER_CALL = 10
YOUTUBE_MAX_RESULTS = 20
RADIUS_MIN_KM = 0.5
RADIUS_MAX_KM = 10.0

# Optional aliases for frequently reused location names.
KNOWN_LOCATION_ALIASES: dict[str, dict[str, float]] = {}

# Optional category list for prompts and docs. The live query path is still user-driven.
DEFAULT_REFERENCE_CATEGORIES = [
    "store",
    "shopping_mall",
    "department_store",
    "supermarket",
    "convenience_store",
    "clothing_store",
    "shoe_store",
    "electronics_store",
    "home_goods_store",
    "furniture_store",
    "hardware_store",
    "pet_store",
    "book_store",
    "jewelry_store",
    "pharmacy",
]

PRICE_TIERS = ["low", "mid", "high"]
