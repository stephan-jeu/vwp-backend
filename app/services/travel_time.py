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


async def get_travel_minutes_batch(
    pairs: list[tuple[str, str]],
) -> dict[tuple[str, str], int]:
    """Fetch travel times for multiple origin-destination pairs in parallel.

    Restricts concurrency to avoid hitting rate limits too aggressively.
    Returns a dictionary mapping (origin, destination) -> minutes.
    Pairs that fail or have no route are omitted/exclude from the result.
    """
    import asyncio

    # Deduplicate pairs
    unique_pairs = list(set(pairs))
    if not unique_pairs:
        return {}

    sem = asyncio.Semaphore(10)  # Max 10 concurrent requests
    results: dict[tuple[str, str], int] = {}

    async def _fetch(pair: tuple[str, str]):
        origin, dest = pair
        async with sem:
            minutes = await get_travel_minutes(origin, dest)
            if minutes is not None:
                results[pair] = minutes

    await asyncio.gather(*[_fetch(p) for p in unique_pairs])
    return results
