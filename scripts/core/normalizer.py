import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from scripts.places_normalize import _normalize_google_place
except ImportError:
    _normalize_google_place = None

@dataclass
class Signal:
    """Unified signal schema for Market Intelligence."""
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""  # google_places | youtube | google_trends
    type: str = ""    # entity | content | metric
    location: Dict[str, Any] = field(default_factory=lambda: {"lat": None, "lng": None, "label": None})
    intensity: float = 0.0  # 0.0 - 1.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "type": self.type,
            "location": self.location,
            "intensity": self.intensity,
            "timestamp": self.timestamp,
            "data": self.data
        }

def normalize_signal(raw_data: dict, source: str) -> dict:
    """
    Normalize raw data from various sources into a unified Signal format.
    
    Args:
        raw_data: The raw dictionary from the source worker.
        source: "google_places", "youtube", or "google_trends".
        
    Returns:
        A dictionary matching the Signal schema.
    """
    signal = Signal(source=source)
    
    if source == "google_places":
        # Check if it looks like a normalized place already
        if "place_id" in raw_data and "name" in raw_data and "source_fetched_at" in raw_data:
            normalized = raw_data
        elif _normalize_google_place:
            normalized = _normalize_google_place(raw_data, area_label=None) or {}
        else:
            normalized = raw_data

        signal.type = "entity"
        signal.location = {
            "lat": normalized.get("lat"),
            "lng": normalized.get("lng"),
            "label": normalized.get("area_label")
        }
        rating = normalized.get("rating")
        if isinstance(rating, (int, float)):
            signal.intensity = round(rating / 5.0, 2)
        else:
            signal.intensity = 0.0
            
        if normalized.get("source_fetched_at"):
            signal.timestamp = normalized["source_fetched_at"]
        
        signal.data = normalized

    elif source == "youtube":
        signal.type = "content"
        areas = raw_data.get("detected_areas", [])
        signal.location = {
            "lat": None,
            "lng": None,
            "label": areas[0] if areas else None
        }
        
        views = raw_data.get("view_count", 0)
        signal.intensity = round(min(views / 1000000.0, 1.0), 2)
        
        if raw_data.get("published_at"):
            signal.timestamp = raw_data["published_at"]
            
        signal.data = {
            "title": raw_data.get("title"),
            "view_count": views,
            "engagement": raw_data.get("like_count", 0) + raw_data.get("comment_count", 0),
            "category": raw_data.get("detected_categories", [])
        }

    elif source == "google_trends":
        signal.type = "metric"
        signal.location = {
            "lat": None,
            "lng": None,
            "label": raw_data.get("geo")
        }
        
        current_val = raw_data.get("current_value", {}).get("value", 0)
        signal.intensity = round(current_val / 100.0, 2)
        
        signal.data = {
            "keyword": raw_data.get("keyword"),
            "interest": raw_data.get("current_value"),
            "peaks": raw_data.get("peak")
        }

    return signal.to_dict()
