"""Entity linker for connecting signals across different sources."""

import re

def link_signals(signals: list[dict]) -> list[dict]:
    """
    Attempt to link signals from different sources.
    
    Currently links YouTube signals to Google Places signals if the YouTube 
    video title or description mentions the Place name.
    
    Args:
        signals: List of normalized signal dictionaries.
        
    Returns:
        List of signals with 'related_signal_ids' field updated where links were found.
    """
    places = [s for s in signals if s["source"] == "google_places"]
    others = [s for s in signals if s["source"] != "google_places"]
    
    for other in others:
        if "related_signal_ids" not in other:
            other["related_signal_ids"] = []
            
        # Only try to link YouTube for now
        if other["source"] == "youtube":
            video_text = (other["data"].get("title", "") + " " + 
                         other["data"].get("description", "")).lower()
            
            for place in places:
                place_name = place["data"].get("name", "").lower()
                if not place_name:
                    continue
                
                # Simple name matching (could be improved with fuzzy matching)
                # Ensure the name is not too short to avoid false positives
                if len(place_name) > 3 and place_name in video_text:
                    if place["signal_id"] not in other["related_signal_ids"]:
                        other["related_signal_ids"].append(place["signal_id"])
                    
                    # Also link back from place to other
                    if "related_signal_ids" not in place:
                        place["related_signal_ids"] = []
                    if other["signal_id"] not in place["related_signal_ids"]:
                        place["related_signal_ids"].append(other["signal_id"])
                        
    return signals
