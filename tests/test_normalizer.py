import pytest
from scripts.core.normalizer import normalize_signal, Signal

def test_signal_dataclass_defaults():
    signal = Signal(source="test", type="test")
    assert signal.signal_id is not None
    assert len(signal.signal_id) > 0
    assert signal.source == "test"
    assert signal.type == "test"
    assert signal.location == {"lat": None, "lng": None, "label": None}
    assert signal.intensity == 0.0
    assert signal.timestamp is not None
    assert signal.data == {}

def test_normalize_google_places():
    raw_data = {
        "place_id": "ChIJ123",
        "name": "Test Place",
        "area_label": "Siam",
        "lat": 13.7,
        "lng": 100.5,
        "rating": 4.5,
        "source_fetched_at": "2026-04-24T00:00:00Z"
    }
    signal_dict = normalize_signal(raw_data, "google_places")
    
    assert signal_dict["source"] == "google_places"
    assert signal_dict["type"] == "entity"
    assert signal_dict["location"] == {"lat": 13.7, "lng": 100.5, "label": "Siam"}
    assert signal_dict["intensity"] == 0.9 # 4.5 / 5.0
    assert signal_dict["timestamp"] == "2026-04-24T00:00:00Z"
    assert signal_dict["data"] == raw_data

def test_normalize_youtube():
    raw_data = {
        "video_id": "abc",
        "title": "Best Ramen in Bangkok",
        "view_count": 500000,
        "like_count": 10000,
        "comment_count": 500,
        "published_at": "2026-04-20T00:00:00Z",
        "detected_areas": ["Siam"],
        "detected_categories": ["casual_dining"]
    }
    signal_dict = normalize_signal(raw_data, "youtube")
    
    assert signal_dict["source"] == "youtube"
    assert signal_dict["type"] == "content"
    assert signal_dict["location"] == {"lat": None, "lng": None, "label": "Siam"}
    assert signal_dict["intensity"] == 0.5 # 500k / 1M
    assert signal_dict["timestamp"] == "2026-04-20T00:00:00Z"
    assert signal_dict["data"]["title"] == "Best Ramen in Bangkok"
    assert signal_dict["data"]["view_count"] == 500000
    assert signal_dict["data"]["engagement"] == 10500
    assert "casual_dining" in signal_dict["data"]["category"]

def test_normalize_google_trends():
    raw_data = {
        "keyword": "ramen",
        "current_value": {"value": 80, "direction": "rising"},
        "peak": {"value": 100, "date": "2026-01-01"},
        "geo": "TH"
    }
    signal_dict = normalize_signal(raw_data, "google_trends")
    
    assert signal_dict["source"] == "google_trends"
    assert signal_dict["type"] == "metric"
    assert signal_dict["location"] == {"lat": None, "lng": None, "label": "TH"}
    assert signal_dict["intensity"] == 0.8 # 80 / 100
    assert signal_dict["data"]["keyword"] == "ramen"
    assert signal_dict["data"]["interest"]["value"] == 80
    assert signal_dict["data"]["peaks"]["value"] == 100
