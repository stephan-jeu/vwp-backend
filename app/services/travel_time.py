from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.travel_time_cache import TravelTimeCache

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
    db: AsyncSession | None = None,
) -> dict[tuple[str, str], int]:
    """Fetch travel times for multiple origin-destination pairs in parallel.

    Restricts concurrency to avoid hitting rate limits too aggressively.
    Returns a dictionary mapping (origin, destination) -> minutes.
    Pairs that fail or have no route are omitted/exclude from the result.
    If a database session is provided, results are cached in the TravelTimeCache table.
    """
    import asyncio

    # Deduplicate pairs
    unique_pairs = list(set(pairs))
    if not unique_pairs:
        return {}

    results: dict[tuple[str, str], int] = {}
    missing_pairs: list[tuple[str, str]] = []

    # 1. Try to fetch from cache first
    if db:
        try:
            # For a large number of pairs, an IN clause with tuples isn't always supported cleanly.
            # We'll fetch all matching origins and destinations and filter in memory, 
            # or issue an OR condition for each pair.
            from sqlalchemy import and_, or_
            
            # Chunk the pairs to avoid massive queries
            chunk_size = 50
            for i in range(0, len(unique_pairs), chunk_size):
                chunk = unique_pairs[i:i + chunk_size]
                
                conditions = [
                    and_(TravelTimeCache.origin == origin, TravelTimeCache.destination == dest)
                    for origin, dest in chunk
                ]
                
                stmt = select(TravelTimeCache).where(or_(*conditions))
                db_results = await db.execute(stmt)
                cached_records = db_results.scalars().all()
                
                for record in cached_records:
                    results[(record.origin, record.destination)] = record.travel_minutes
                    
            # Identify which pairs are still missing
            for pair in unique_pairs:
                if pair not in results:
                    missing_pairs.append(pair)
                    
        except Exception as exc:
            _logger.error("Failed to read travel time from cache: %s", exc)
            missing_pairs = unique_pairs
    else:
        missing_pairs = unique_pairs

    if not missing_pairs:
        return results

    # 2. Fetch missing pairs from Google Maps
    sem = asyncio.Semaphore(10)  # Max 10 concurrent requests
    new_cache_entries = []

    async def _fetch(pair: tuple[str, str]):
        origin, dest = pair
        async with sem:
            minutes = await get_travel_minutes(origin, dest)
            if minutes is not None:
                results[pair] = minutes
                new_cache_entries.append(TravelTimeCache(origin=origin, destination=dest, travel_minutes=minutes))

    await asyncio.gather(*[_fetch(p) for p in missing_pairs])

    # 3. Save new results to cache
    if db and new_cache_entries:
        try:
            db.add_all(new_cache_entries)
            await db.commit()
        except Exception as exc:
            _logger.error("Failed to save travel time to cache: %s", exc)
            await db.rollback()

    return results
