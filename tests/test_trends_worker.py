import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime

from scripts.workers.trends_worker import fetch_trends

@patch("scripts.workers.trends_worker.TrendReq")
def test_fetch_trends_structure(mock_trend_req):
    # Setup mock
    mock_instance = mock_trend_req.return_value
    
    # Mock interest_over_time
    dates = pd.date_range(start="2023-01-01", periods=10, freq="W")
    mock_iot = pd.DataFrame({
        "matcha": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        "isPartial": [False] * 10
    }, index=dates)
    mock_instance.interest_over_time.return_value = mock_iot
    
    # Run function
    result = fetch_trends(keywords=["matcha"], geo="TH", timeframe="today 12-m")
    
    # Verify structure
    assert result["status"] == "ok"
    assert result["keywords"] == ["matcha"]
    assert result["geo"] == "TH"
    assert result["timeframe"] == "today 12-m"
    assert "interest_over_time" in result
    assert "current_values" in result
    assert "peaks" in result
    
    # Verify data
    assert len(result["interest_over_time"]["matcha"]) == 10
    assert result["current_values"]["matcha"]["value"] == 100
    assert result["current_values"]["matcha"]["direction"] == "rising"
    assert result["peaks"]["matcha"]["value"] == 100
    assert result["peaks"]["matcha"]["date"] == dates[-1].strftime("%Y-%m-%d")

@patch("scripts.workers.trends_worker.TrendReq")
def test_fetch_trends_with_related(mock_trend_req):
    # Setup mock
    mock_instance = mock_trend_req.return_value
    
    # Mock interest_over_time
    dates = pd.date_range(start="2023-01-01", periods=5, freq="W")
    mock_iot = pd.DataFrame({
        "matcha": [10, 20, 30, 40, 50],
        "isPartial": [False] * 5
    }, index=dates)
    mock_instance.interest_over_time.return_value = mock_iot
    
    # Mock related_queries
    mock_related = {
        "matcha": {
            "rising": pd.DataFrame({"query": ["matcha tea"], "value": [100]}),
            "top": pd.DataFrame({"query": ["matcha"], "value": [100]})
        }
    }
    mock_instance.related_queries.return_value = mock_related
    
    # Run function
    result = fetch_trends(keywords=["matcha"], related=True)
    
    # Verify related queries
    assert "related_queries" in result
    assert "matcha" in result["related_queries"]
    assert len(result["related_queries"]["matcha"]["rising"]) == 1
    assert result["related_queries"]["matcha"]["rising"][0]["query"] == "matcha tea"
    assert result["related_queries"]["matcha"]["rising"][0]["growth"] == "+100%"
