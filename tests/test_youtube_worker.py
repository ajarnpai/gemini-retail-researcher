import json
from unittest.mock import MagicMock, patch
import pytest
import httpx
from scripts.workers.youtube_worker import fetch_youtube_signals

@pytest.fixture
def mock_httpx_client():
    # Store the real class before patching
    real_client_class = httpx.Client
    with patch("httpx.Client") as mock_client_class:
        mock_client = MagicMock(spec=real_client_class)
        mock_client_class.return_value.__enter__.return_value = mock_client
        yield mock_client

def test_fetch_youtube_signals_no_api_key(monkeypatch):
    monkeypatch.setattr("scripts.workers.youtube_worker.YOUTUBE_API_KEY", "")
    result = fetch_youtube_signals("test query")
    assert result["status"] == "error"
    assert result["error_code"] == "no_youtube_api_key"

def test_fetch_youtube_signals_success(mock_httpx_client, monkeypatch):
    monkeypatch.setattr("scripts.workers.youtube_worker.YOUTUBE_API_KEY", "fake_key")
    
    # Mock search response
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "items": [
            {
                "id": {"videoId": "vid1"},
                "snippet": {"channelId": "ch1"}
            }
        ]
    }
    
    # Mock videos response
    mock_videos_resp = MagicMock()
    mock_videos_resp.status_code = 200
    mock_videos_resp.json.return_value = {
        "items": [
            {
                "id": "vid1",
                "snippet": {
                    "title": "Best Ramen in Ari",
                    "description": "Checking out this cool ramen spot in Ari.",
                    "tags": ["ramen", "ari", "bangkok"],
                    "publishedAt": "2026-04-20T10:00:00Z",
                    "channelId": "ch1",
                    "channelTitle": "Foodie Channel"
                },
                "statistics": {
                    "viewCount": "1000",
                    "likeCount": "100",
                    "commentCount": "10"
                }
            }
        ]
    }
    
    # Mock channels response
    mock_channels_resp = MagicMock()
    mock_channels_resp.status_code = 200
    mock_channels_resp.json.return_value = {
        "items": [
            {
                "id": "ch1",
                "snippet": {"title": "Foodie Channel"},
                "statistics": {
                    "subscriberCount": "5000",
                    "viewCount": "50000",
                    "video_count": "50"
                }
            }
        ]
    }
    
    # Set side effect for get calls
    def side_effect(url, params):
        if "search" in url: return mock_search_resp
        if "videos" in url: return mock_videos_resp
        if "channels" in url: return mock_channels_resp
        return MagicMock(status_code=404)
        
    mock_httpx_client.get.side_effect = side_effect
    
    result = fetch_youtube_signals("ramen ari")
    
    assert result["status"] == "ok"
    assert result["video_count"] == 1
    assert result["videos"][0]["video_id"] == "vid1"
    assert "casual_dining" in result["videos"][0]["detected_categories"]
    assert "ari" in result["videos"][0]["detected_areas"]
    assert len(result["creators_discovered"]) == 1
    assert result["creators_discovered"][0]["channel_id"] == "ch1"
    assert result["signals_extracted"][0]["theme"] == "casual_dining"

def test_fetch_youtube_signals_quota_error(mock_httpx_client, monkeypatch):
    monkeypatch.setattr("scripts.workers.youtube_worker.YOUTUBE_API_KEY", "fake_key")
    
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Quota exceeded"
    mock_httpx_client.get.return_value = mock_resp
    
    result = fetch_youtube_signals("test query")
    assert result["status"] == "error"
    assert result["error_code"] == "youtube_quota_exceeded"
