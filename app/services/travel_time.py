from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

_logger = logging.getLogger("uvicorn.error")

GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


async def get_travel_minutes(origin: str, destination: str) -> Optional[int]:
    """Return driving travel time in minutes between origin and destination.

    Uses Google Directions API. Returns None if API key missing or on failure.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        _logger.warning("Google Maps API key not set; skipping travel time calculation")
        return None

    params = {
        "origin": origin,
        "destination": destination,
        "mode": "driving",
        "key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_DIRECTIONS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            routes = data.get("routes") or []
            if not routes:
                _logger.warning(
                    "No routes from Google Directions for %s -> %s", origin, destination
                )
                return None
            legs = (routes[0] or {}).get("legs") or []
            if not legs:
                return None
            seconds = (legs[0].get("duration") or {}).get("value")
            if not isinstance(seconds, int):
                return None
            return max(0, seconds // 60)
    except Exception as exc:
        _logger.error("Travel time lookup failed: %s", exc)
        return None
