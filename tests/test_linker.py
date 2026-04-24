"""Unit test for the entity linker."""

import pytest
from scripts.core.linker import link_signals

def test_link_signals_youtube_to_places():
    signals = [
        {
            "signal_id": "p1",
            "source": "google_places",
            "data": {"name": "Sarnies Bangkok"}
        },
        {
            "signal_id": "y1",
            "source": "youtube",
            "data": {"title": "Best coffee at Sarnies Bangkok", "description": "Reviewing Sarnies"}
        },
        {
            "signal_id": "y2",
            "source": "youtube",
            "data": {"title": "Exploring Bangkok", "description": "No mention here"}
        }
    ]
    
    linked = link_signals(signals)
    
    # y1 should be linked to p1
    y1 = next(s for s in linked if s["signal_id"] == "y1")
    assert "p1" in y1["related_signal_ids"]
    
    # p1 should be linked to y1
    p1 = next(s for s in linked if s["signal_id"] == "p1")
    assert "y1" in p1["related_signal_ids"]
    
    # y2 should not be linked to p1
    y2 = next(s for s in linked if s["signal_id"] == "y2")
    assert "p1" not in y2["related_signal_ids"]
