"""Geocoding service voor Nederlandse adressen.

Gebruikt PDOK Locatieserver als primaire bron (gratis, NL overheidsdienst).
Valt terug op Google Maps Geocoding als PDOK geen resultaat geeft.
"""

from __future__ import annotations

import logging
import os
import re

import httpx

_logger = logging.getLogger("uvicorn.error")

PDOK_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
GOOGLE_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Patroon voor WKT POINT-notatie: "POINT(lon lat)"
_POINT_RE = re.compile(r"POINT\(([0-9.\-]+)\s+([0-9.\-]+)\)")


async def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocodeer een adres naar (lat, lon) coördinaten.

    Probeert eerst PDOK Locatieserver (gratis, NL-specifiek).
    Valt terug op Google Maps Geocoding API als PDOK niets vindt.

    Args:
        address: Adresstring, bijv. "Kerkstraat 1, Lelystad" of "Lelystad".

    Returns:
        (lat, lon) tuple in WGS84 of None bij mislukking.
    """
    if not address or not address.strip():
        return None

    coords = await _geocode_pdok(address.strip())
    if coords:
        return coords

    coords = await _geocode_google(address.strip())
    return coords


async def _geocode_pdok(address: str) -> tuple[float, float] | None:
    """Geocodeer via PDOK Locatieserver."""
    params = {
        "q": address,
        "rows": 1,
        "fq": "type:(adres gemeente woonplaats)",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(PDOK_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        docs = (data.get("response") or {}).get("docs") or []
        if not docs:
            return None

        # centroide_ll is WKT: "POINT(lon lat)"
        centroide = docs[0].get("centroide_ll") or ""
        m = _POINT_RE.match(centroide)
        if not m:
            return None

        lon = float(m.group(1))
        lat = float(m.group(2))
        return (lat, lon)

    except Exception as exc:
        _logger.debug("PDOK geocoding mislukt voor '%s': %s", address, exc)
        return None


async def _geocode_google(address: str) -> tuple[float, float] | None:
    """Geocodeer via Google Maps Geocoding API als fallback."""
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None

    params = {
        "address": address,
        "key": api_key,
        "region": "nl",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(GOOGLE_GEOCODING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results") or []
        if not results:
            return None

        location = (results[0].get("geometry") or {}).get("location") or {}
        lat = location.get("lat")
        lng = location.get("lng")
        if lat is None or lng is None:
            return None

        return (float(lat), float(lng))

    except Exception as exc:
        _logger.debug("Google geocoding mislukt voor '%s': %s", address, exc)
        return None
