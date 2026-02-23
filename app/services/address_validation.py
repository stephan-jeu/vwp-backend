from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Optional

import httpx

_logger = logging.getLogger("uvicorn.error")

GOOGLE_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"


async def is_valid_address(address: str) -> bool | None:
    """Validate an address using the Google Maps Geocoding API.

    Returns:
        True if the address is valid and successfully geocoded to a location.
        False if the address could not be found or geocoded.
        None if the API key is missing or an HTTP/API error occurred.
    """
    if not address or not address.strip():
        return False

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        _logger.warning("Google Maps API key not set; skipping address validation")
        return None

    params = {
        "address": address.strip(),
        "key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_GEOCODING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            # https://developers.google.com/maps/documentation/geocoding/requests-geocoding#StatusCodes
            status = data.get("status")
            if status == "OK":
                return True
            if status == "ZERO_RESULTS":
                return False
                
            _logger.warning("Unexpected Google Geocoding status: %s for address: %s", status, address)
            return None
    except Exception as exc:
        _logger.error("Address validation lookup failed: %s", exc)
        return None
