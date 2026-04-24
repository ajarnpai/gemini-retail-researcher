"""Worker for fetching Google Trends data."""

import logging
from pytrends.request import TrendReq

logger = logging.getLogger(__name__)

def fetch_trends(keywords: list[str], geo: str = "TH", timeframe: str = "today 12-m", related: bool = False) -> dict:
    """
    Fetch Google Trends data for keywords.
    
    Args:
        keywords: List of keywords to search (max 5).
        geo: Geographic region (default: TH).
        timeframe: Timeframe (default: today 12-m).
        related: Whether to fetch related queries.
        
    Returns:
        A dictionary with status, keywords, geo, timeframe, interest_over_time, 
        current_values, peaks, and (optionally) related_queries.
    """
    if not keywords:
        return {"status": "error", "error_code": "invalid_query", "message": "Keywords list cannot be empty"}
        
    if len(keywords) > 5:
        return {"status": "error", "error_code": "invalid_query", "message": "Maximum 5 keywords per request (Google Trends limit)"}

    try:
        # hl="en-US", tz=420 (Bangkok time)
        pytrends = TrendReq(hl="en-US", tz=420)
        pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo)

        # Interest over time
        iot = pytrends.interest_over_time()

        interest_over_time = {}
        current_values = {}
        peaks = {}

        if not iot.empty:
            for kw in keywords:
                if kw in iot.columns:
                    series = iot[kw]
                    interest_over_time[kw] = [
                        {"date": idx.strftime("%Y-%m-%d"), "value": int(val)}
                        for idx, val in series.items()
                    ]

                    # Basic analysis
                    current = int(series.iloc[-1])
                    previous = int(series.iloc[-5]) if len(series) > 5 else int(series.iloc[0])
                    if current > previous:
                        direction = "rising"
                    elif current < previous:
                        direction = "declining"
                    else:
                        direction = "stable"

                    current_values[kw] = {
                        "value": current,
                        "direction": direction,
                        "previous": previous,
                    }

                    peak_val = int(series.max())
                    peak_date = series.idxmax().strftime("%Y-%m-%d")
                    peaks[kw] = {"value": peak_val, "date": peak_date}

        # Related queries (optional, one API call per keyword)
        related_queries = {}
        if related:
            for kw in keywords:
                try:
                    pytrends.build_payload([kw], cat=0, timeframe=timeframe, geo=geo)
                    related_data = pytrends.related_queries()
                    kw_related = {"rising": [], "top": []}

                    if kw in related_data:
                        if related_data[kw]["rising"] is not None:
                            for _, row in related_data[kw]["rising"].head(10).iterrows():
                                # Handle cases where value might not be an int (e.g. 'Breakout')
                                val = row["value"]
                                growth = f"+{val}%" if isinstance(val, (int, float)) else str(val)
                                kw_related["rising"].append({
                                    "query": row["query"],
                                    "growth": growth,
                                })
                        if related_data[kw]["top"] is not None:
                            for _, row in related_data[kw]["top"].head(10).iterrows():
                                kw_related["top"].append({
                                    "query": row["query"],
                                    "value": int(row["value"]),
                                })

                    related_queries[kw] = kw_related
                except Exception as e:
                    logger.error(f"Failed to fetch related queries for {kw}: {e}")
                    related_queries[kw] = {"rising": [], "top": [], "error": str(e)}

        result = {
            "status": "ok",
            "keywords": keywords,
            "geo": geo,
            "timeframe": timeframe,
            "interest_over_time": interest_over_time,
            "current_values": current_values,
            "peaks": peaks,
        }
        if related:
            result["related_queries"] = related_queries

        return result

    except Exception as e:
        logger.error(f"Google Trends request failed: {e}")
        return {"status": "error", "error_code": "upstream_unavailable", "message": f"Google Trends request failed: {e}"}
