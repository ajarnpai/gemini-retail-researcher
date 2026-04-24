"""Worker for fetching YouTube video signals and extracting trends."""

import logging
import time
from collections import Counter
from datetime import datetime, timezone
import httpx
from scripts.config import YOUTUBE_API_KEY

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# --- Detection Constants (Refactored from legacy) ---
KNOWN_CHAINS = [
    "Bankara Ramen", "Sizzler", "MK Restaurant", "Fuji", "S&P",
    "After You", "Bar B Q Plaza", "Bonchon", "CoCo Ichibanya",
    "Haidilao", "Ootoya", "Pepper Lunch", "Shabushi", "Yayoi",
    "McDonald's", "KFC", "Pizza Hut", "Starbucks", "Tim Hortons",
    "The Pizza Company", "Chester's Grill", "Suki Teenoi",
    "Mos Burger", "Yoshinoya", "Marugame Seimen",
]

BANGKOK_NEIGHBORHOODS = [
    "ari", "silom", "sukhumvit", "sathorn", "thonglor", "ekkamai",
    "siam", "chinatown", "khao_san", "asoke", "phrom_phong",
    "on_nut", "bang_rak", "ratchada", "ladprao"
]

CONCEPT_TYPE_RULES = [
    {"keywords": ["food_court", "fast_food", "quick_bite"], "concept_type": "fast_casual"},
    {"keywords": ["restaurant", "dining"], "concept_type": "casual_dining"},
    {"keywords": ["fine_dining", "tasting_menu"], "concept_type": "fine_dining"},
    {"keywords": ["cafe", "coffee", "bakery", "dessert"], "concept_type": "cafe_bakery"},
    {"keywords": ["street_food", "hawker", "stall", "market"], "concept_type": "street_food"},
    {"keywords": ["bar", "pub", "izakaya", "gastropub"], "concept_type": "bar_restaurant"},
    {"keywords": ["delivery", "cloud_kitchen", "virtual"], "concept_type": "delivery_focused"},
]

# --- Detection Helpers ---

def detect_categories(title: str, description: str, tags: list[str]) -> list[str]:
    text = (title + " " + description + " " + " ".join(tags)).lower()
    categories = set()
    for rule in CONCEPT_TYPE_RULES:
        if any(kw in text for kw in rule["keywords"]):
            categories.add(rule["concept_type"])
    return list(categories) if categories else ["casual_dining"]

def detect_areas(text: str) -> list[str]:
    text_lower = text.lower()
    areas = [area for area in BANGKOK_NEIGHBORHOODS if area in text_lower]
    return areas

def detect_chains(text: str) -> list[str]:
    text_lower = text.lower()
    chains = [chain for chain in KNOWN_CHAINS if chain.lower() in text_lower]
    return chains

def map_follower_tier(subs: int) -> str:
    if subs >= 1_000_000: return "mega"
    if subs >= 100_000: return "macro"
    if subs >= 50_000: return "mid"
    if subs >= 10_000: return "micro"
    return "nano"

def map_engagement_level(avg_views: int, subs: int) -> str:
    if subs == 0: return "low"
    rate = avg_views / subs
    if rate > 0.5: return "viral"
    if rate > 0.2: return "high"
    if rate > 0.05: return "moderate"
    return "low"

def _is_recent(published_at: str, days: int = 30) -> bool:
    if not published_at:
        return False
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        now = datetime.now(tz=timezone.utc)
        return (now - dt).days <= days
    except (ValueError, TypeError):
        return False

# --- API Interaction ---

def _get_api(client: httpx.Client, endpoint: str, params: dict):
    """GET request to YouTube API with error handling."""
    try:
        resp = client.get(f"{YOUTUBE_API_BASE}/{endpoint}", params=params)
        
        if resp.status_code == 403:
            body = resp.text.lower()
            if "quota" in body or "quotaexceeded" in body or "dailylimitexceeded" in body:
                return {"status": "error", "error_code": "youtube_quota_exceeded", "message": "YouTube API quota exceeded"}
            return {"status": "error", "error_code": "youtube_forbidden", "message": f"YouTube API returned 403: {resp.text[:200]}"}
            
        if resp.status_code != 200:
            return {"status": "error", "error_code": "youtube_unavailable", "message": f"YouTube API returned {resp.status_code}: {resp.text[:200]}"}
            
        return {"status": "ok", "data": resp.json()}
    except Exception as e:
        logger.error(f"YouTube API request failed: {e}")
        return {"status": "error", "error_code": "upstream_unavailable", "message": str(e)}

def fetch_youtube_signals(query: str, max_results: int = 20, geo: str = "TH") -> dict:
    """
    Fetch YouTube videos and extract signals.
    """
    if not YOUTUBE_API_KEY:
        return {"status": "error", "error_code": "no_youtube_api_key", "message": "YOUTUBE_API_KEY not set"}

    quota_used = 0
    max_results = min(max(1, max_results), 50)

    with httpx.Client(timeout=30.0) as client:
        # Step 1: Search
        search_params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "regionCode": geo,
            "maxResults": max_results,
            "key": YOUTUBE_API_KEY,
        }
        search_res = _get_api(client, "search", search_params)
        if search_res["status"] == "error":
            return search_res
        
        quota_used += 100
        items = search_res["data"].get("items", [])
        if not items:
            return {"status": "ok", "query": query, "video_count": 0, "videos": [], "creators_discovered": [], "signals_extracted": []}

        video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]
        channel_ids = list({item["snippet"]["channelId"] for item in items if item.get("snippet", {}).get("channelId")})

        # Step 2: Video details
        videos_params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
            "key": YOUTUBE_API_KEY,
        }
        videos_res = _get_api(client, "videos", videos_params)
        if videos_res["status"] == "error":
            return videos_res
        
        quota_used += 1
        video_details = {v["id"]: v for v in videos_res["data"].get("items", [])}

        # Step 3: Channel details
        channel_data_map = {}
        if channel_ids:
            channels_params = {
                "part": "snippet,statistics",
                "id": ",".join(channel_ids),
                "key": YOUTUBE_API_KEY,
            }
            channels_res = _get_api(client, "channels", channels_params)
            if channels_res["status"] == "error":
                return channels_res
            
            quota_used += 1
            for ch in channels_res["data"].get("items", []):
                channel_data_map[ch["id"]] = ch

    # --- Processing ---
    videos_out = []
    all_detected_categories = []

    for vid_id in video_ids:
        detail = video_details.get(vid_id)
        if not detail: continue

        snippet = detail.get("snippet", {})
        stats = detail.get("statistics", {})

        title = snippet.get("title", "")
        description = snippet.get("description", "")
        tags = snippet.get("tags", [])
        published_at = snippet.get("publishedAt", "")
        channel_id = snippet.get("channelId", "")

        view_count = int(stats.get("viewCount", 0))
        like_count = int(stats.get("likeCount", 0))
        comment_count = int(stats.get("commentCount", 0))

        detection_text = f"{title} {description} {' '.join(tags)}"
        categories = detect_categories(title, description, tags)
        areas = detect_areas(detection_text)
        chains = detect_chains(detection_text)
        
        all_detected_categories.extend(categories)

        videos_out.append({
            "video_id": vid_id,
            "title": title,
            "description": description[:500],
            "channel_id": channel_id,
            "channel_title": snippet.get("channelTitle", ""),
            "published_at": published_at,
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": comment_count,
            "tags": tags,
            "url": f"https://www.youtube.com/watch?v={vid_id}",
            "detected_categories": categories,
            "detected_areas": areas,
            "detected_chains": chains,
        })

    creators_discovered = []
    seen_channels = set()
    for vid in videos_out:
        ch_id = vid["channel_id"]
        if ch_id in seen_channels: continue
        seen_channels.add(ch_id)

        ch_data = channel_data_map.get(ch_id, {})
        ch_snippet = ch_data.get("snippet", {})
        ch_stats = ch_data.get("statistics", {})

        subs = int(ch_stats.get("subscriberCount", 0))
        total_views = int(ch_stats.get("viewCount", 0))
        video_count = int(ch_stats.get("videoCount", 1))
        avg_views = total_views // max(video_count, 1)

        creators_discovered.append({
            "channel_id": ch_id,
            "channel_title": ch_snippet.get("title", vid["channel_title"]),
            "subscriber_count": subs,
            "follower_tier": map_follower_tier(subs),
            "engagement_level": map_engagement_level(avg_views, subs),
        })

    signals_extracted = []
    if all_detected_categories:
        counts = Counter(all_detected_categories)
        top_cat, top_count = counts.most_common(1)[0]
        
        confidence = 0.50
        if top_count > 1: confidence += 0.10
        
        theme_recent = any(
            _is_recent(v["published_at"])
            for v in videos_out
            if top_cat in v["detected_categories"]
        )
        if theme_recent: confidence += 0.10
        
        signals_extracted.append({
            "source": "youtube",
            "theme": top_cat,
            "format": "video review",
            "confidence": round(min(confidence, 1.0), 2),
        })

    return {
        "status": "ok",
        "query": query,
        "video_count": len(videos_out),
        "quota_used": quota_used,
        "videos": videos_out,
        "creators_discovered": creators_discovered,
        "signals_extracted": signals_extracted,
    }
