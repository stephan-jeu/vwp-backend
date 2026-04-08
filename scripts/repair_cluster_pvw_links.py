"""Repair protocol-visit-window links for one or more clusters.

Usage:
    # Repair specific clusters:
    python scripts/repair_cluster_pvw_links.py --clusters 42 107 215

    # Repair ALL clusters (use with care on large databases):
    python scripts/repair_cluster_pvw_links.py --all

    # Dry-run: show what would change without writing:
    python scripts/repair_cluster_pvw_links.py --all --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, text  # noqa: E402

from app.models.cluster import Cluster  # noqa: E402
from app.services.pvw_sync_service import sync_cluster_pvw_links  # noqa: E402
from db.session import AsyncSessionLocal  # noqa: E402


async def repair(cluster_ids: list[int] | None, dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        if cluster_ids is None:
            # Fetch all non-deleted cluster IDs
            rows = (
                await db.execute(
                    select(Cluster.id).where(Cluster.deleted_at.is_(None)).order_by(Cluster.id)
                )
            ).scalars().all()
            cluster_ids = list(rows)

        print(f"Repairing {len(cluster_ids)} cluster(s){' [DRY RUN]' if dry_run else ''}...")

        for cluster_id in cluster_ids:
            await sync_cluster_pvw_links(db, cluster_id)
            print(f"  cluster {cluster_id}: done")

        if dry_run:
            await db.rollback()
            print("Dry run — rolled back all changes.")
        else:
            await db.commit()
            print("Committed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair cluster PVW links.")
    parser.add_argument(
        "--clusters",
        nargs="+",
        type=int,
        metavar="CLUSTER_ID",
        help="One or more cluster IDs to repair.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_clusters",
        help="Repair all clusters.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute changes but roll back — nothing is written to the database.",
    )
    args = parser.parse_args()

    if not args.clusters and not args.all_clusters:
        parser.error("Provide --clusters ID [ID ...] or --all.")
    if args.clusters and args.all_clusters:
        parser.error("--clusters and --all are mutually exclusive.")

    ids = None if args.all_clusters else args.clusters

    asyncio.run(repair(ids, args.dry_run))


if __name__ == "__main__":
    main()
