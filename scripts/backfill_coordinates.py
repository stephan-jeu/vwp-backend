"""Backfill lat/lon coördinaten voor bestaande clusters en gebruikers.

Geocodeert alle clusters en gebruikers met lat=NULL via PDOK Locatieserver
(gratis, NL overheidsdienst) met Google Maps als fallback.

Gebruik:
    cd backend
    python scripts/backfill_coordinates.py

Optioneel: alleen clusters of alleen users:
    python scripts/backfill_coordinates.py --only clusters
    python scripts/backfill_coordinates.py --only users

Dry-run (toont wat gedaan zou worden, slaat niets op):
    python scripts/backfill_coordinates.py --dry-run
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Backend root op het pad zetten zodat imports werken
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.models.cluster import Cluster
from app.models.user import User
from app.services.geocoding import geocode_address
from db.session import AsyncSessionLocal


async def _geocode_address_for_cluster(cluster: Cluster) -> str | None:
    """Stel het geocodeer-adres samen voor een cluster."""
    address = (getattr(cluster, "address", None) or "").strip()
    if not address or address == "-":
        return None

    location = getattr(cluster, "location", None)
    if not location:
        project = getattr(cluster, "project", None)
        location = getattr(project, "location", None) if project else None

    return f"{address}, {location}" if location else address


async def backfill_clusters(db, dry_run: bool) -> tuple[int, int, int]:
    """Geocodeer clusters zonder coördinaten. Geeft (totaal, gevonden, mislukt) terug."""
    from sqlalchemy.orm import selectinload

    stmt = (
        select(Cluster)
        .where(Cluster.deleted_at.is_(None))
        .where(Cluster.lat.is_(None))
        .options(selectinload(Cluster.project))
        .order_by(Cluster.id)
    )
    clusters = (await db.execute(stmt)).scalars().all()

    total = len(clusters)
    found = 0
    failed = 0

    print(f"\nClusters zonder coördinaten: {total}")

    for cluster in clusters:
        query = await _geocode_address_for_cluster(cluster)
        if not query:
            print(f"  [SKIP] cluster {cluster.id}: geen bruikbaar adres")
            failed += 1
            continue

        coords = await geocode_address(query)
        if coords:
            lat, lon = coords
            print(f"  [OK]   cluster {cluster.id} ({query!r}) → lat={lat:.5f}, lon={lon:.5f}")
            if not dry_run:
                cluster.lat = lat
                cluster.lon = lon
            found += 1
        else:
            print(f"  [FAIL] cluster {cluster.id} ({query!r}) → geen resultaat")
            failed += 1

        # Kleine pauze om PDOK niet te overbelasten
        await asyncio.sleep(0.05)

    if not dry_run and found > 0:
        await db.commit()
        print(f"\nClusters opgeslagen: {found} geüpdatet.")

    return total, found, failed


async def backfill_users(db, dry_run: bool) -> tuple[int, int, int]:
    """Geocodeer gebruikers zonder coördinaten. Geeft (totaal, gevonden, mislukt) terug."""
    stmt = (
        select(User)
        .where(User.deleted_at.is_(None))
        .where(User.lat.is_(None))
        .where((User.address.is_not(None)) | (User.city.is_not(None)))
        .order_by(User.id)
    )
    users = (await db.execute(stmt)).scalars().all()

    total = len(users)
    found = 0
    failed = 0

    print(f"\nGebruikers zonder coördinaten (met adres/stad): {total}")

    for user in users:
        query = user.address or user.city
        if not query or not query.strip():
            failed += 1
            continue

        coords = await geocode_address(query.strip())
        if coords:
            lat, lon = coords
            name = user.full_name or user.email
            print(f"  [OK]   user {user.id} ({name!r}, {query!r}) → lat={lat:.5f}, lon={lon:.5f}")
            if not dry_run:
                user.lat = lat
                user.lon = lon
            found += 1
        else:
            name = user.full_name or user.email
            print(f"  [FAIL] user {user.id} ({name!r}, {query!r}) → geen resultaat")
            failed += 1

        await asyncio.sleep(0.05)

    if not dry_run and found > 0:
        await db.commit()
        print(f"\nGebruikers opgeslagen: {found} geüpdatet.")

    return total, found, failed


async def main(only: str | None, dry_run: bool) -> None:
    if dry_run:
        print("=== DRY-RUN modus: er wordt niets opgeslagen ===")

    async with AsyncSessionLocal() as db:
        cluster_stats = (0, 0, 0)
        user_stats = (0, 0, 0)

        if only in (None, "clusters"):
            cluster_stats = await backfill_clusters(db, dry_run)

        if only in (None, "users"):
            user_stats = await backfill_users(db, dry_run)

    print("\n=== Samenvatting ===")
    if only in (None, "clusters"):
        total, found, failed = cluster_stats
        print(f"Clusters: {total} totaal, {found} geocodeerd, {failed} mislukt/overgeslagen")
    if only in (None, "users"):
        total, found, failed = user_stats
        print(f"Users:    {total} totaal, {found} geocodeerd, {failed} mislukt/overgeslagen")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill lat/lon coördinaten")
    parser.add_argument(
        "--only",
        choices=["clusters", "users"],
        default=None,
        help="Alleen clusters of alleen users backfillen (standaard: beide)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Toon wat gedaan zou worden zonder op te slaan",
    )
    args = parser.parse_args()

    asyncio.run(main(only=args.only, dry_run=args.dry_run))
