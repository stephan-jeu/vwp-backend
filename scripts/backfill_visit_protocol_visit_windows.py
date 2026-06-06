from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.models.cluster import Cluster  # noqa: E402
from app.services.pvw_sync_service import sync_cluster_pvw_links  # noqa: E402
from db.session import AsyncSessionLocal  # noqa: E402


async def run_backfill_script(dry_run: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Cluster.id).where(Cluster.deleted_at.is_(None)).order_by(Cluster.id)
            )
        ).scalars().all()
        cluster_ids = list(rows)

        mode = "DRY RUN — " if dry_run else ""
        print(f"{mode}Syncing PVW links for {len(cluster_ids)} cluster(s)...")

        total_added = 0
        total_removed = 0
        changed_clusters: list[tuple[int, int, int]] = []

        for cluster_id in cluster_ids:
            added, removed = await sync_cluster_pvw_links(db, cluster_id)
            if added or removed:
                changed_clusters.append((cluster_id, added, removed))
                total_added += added
                total_removed += removed

        if changed_clusters:
            print(f"\nClusters with changes ({len(changed_clusters)}):")
            for cluster_id, added, removed in changed_clusters:
                print(f"  cluster {cluster_id}: +{added} / -{removed}")
            print(f"\nTotal: +{total_added} added, -{total_removed} removed")
        else:
            print("No changes needed.")

        if dry_run:
            await db.rollback()
            print("\nDRY RUN — nothing committed. Run without --dry-run to apply.")
        else:
            await db.commit()
            print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill visit-protocol-visit-window links.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without committing.",
    )
    args = parser.parse_args()
    asyncio.run(run_backfill_script(dry_run=args.dry_run))
