import asyncio
import sys
import os
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Add app to path
sys.path.append(os.getcwd())

from db.session import AsyncSessionLocal
from app.models.visit import Visit
from app.models.user import User
from app.models.species import Species
from app.models.protocol import Protocol
from app.models.cluster import Cluster
from app.models.project import Project
from app.services.visit_planning_selection import (
    _qualifies_user_for_visit, 
    _load_user_daypart_capacities,
    _user_has_capacity_for_visit,
    _load_user_capacities
)
from app.services.visit_status_service import derive_visit_status

async def debug_visit(visit_id: int):
    # Quick hack to parse args manually
    target_week = None
    if len(sys.argv) > 2:
        try:
            target_week = int(sys.argv[2])
        except:
            pass

    print(f"--- DEBUGGING VISIT {visit_id} (Target Week: {target_week or 'Auto'}) ---")
    
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Visit)
            .where(Visit.id == visit_id)
            .options(
                selectinload(Visit.functions),
                selectinload(Visit.species).selectinload(Species.family),
                selectinload(Visit.researchers),
                selectinload(Visit.cluster).selectinload(Cluster.project),
            )
        )
        visit = (await db.execute(stmt)).scalars().first()
        
        if not visit:
            print(f"Visit {visit_id} not found!")
            return

        print(f"Visit: {visit.cluster.project.code} / {visit.cluster.address}")
        print(f"Functions: {[f.name for f in visit.functions]}")
        print(f"Species: {[s.name for s in visit.species]}")
        print(f"Flags: WBC={visit.wbc}, Fiets={visit.fiets}, HUB={visit.hub}, DVP={visit.dvp}, Sleutel={visit.sleutel}")
        print(f"Window: {visit.from_date} -> {visit.to_date}")
        print(f"Required Part: {visit.part_of_day}")

        status = derive_visit_status(visit, None)
        print(f"Status Code: {status}")
        
        if status != 10 and str(status) != "open": 
            print(f"WARNING: Visit is NOT OPEN ({status}). It will be skipped by planner.")

        # Determine week to check capacity for
        week_to_check = target_week
        if not week_to_check:
            if visit.planned_week:
                week_to_check = visit.planned_week
                print(f"Using visit's planned_week: {week_to_check}")
            elif visit.from_date:
                week_to_check = visit.from_date.isocalendar().week
                print(f"Using visit's from_date week: {week_to_check}")
            else:
                week_to_check = date.today().isocalendar().week
                print(f"Defaulting to current week: {week_to_check}")
                
        # Load capacities
        print(f"Loading capacities for Week {week_to_check}...")
        user_caps = await _load_user_daypart_capacities(db, week_to_check)
        
        print("\n--- QUALIFICATION & CAPACITY CHECK ---")
        users = (await db.execute(select(User).order_by(User.full_name))).scalars().all()
        
        qualified_count = 0
        capacity_count = 0
        
        for u in users:
            # Skip soft deleted
            if getattr(u, 'deleted_at', None) is not None:
                continue
            
            qualifies = _qualifies_user_for_visit(u, visit)
            
            if qualifies:
                caps = user_caps.get(u.id, {})
                pod = visit.part_of_day or "Dag" # Default fallback
                
                # Check specific capacity
                has_cap = _user_has_capacity_for_visit(user_caps, u.id, pod)
                
                cap_str = f"Caps: {caps}"
                if has_cap:
                    print(f"[OK] {u.full_name} ({u.id}) - {cap_str}")
                    capacity_count += 1
                else:
                    print(f"[NO_CAP] {u.full_name} ({u.id}) - {cap_str} (Needed: {pod})")
                
                qualified_count += 1
            else:
                # Diagnostics
                msg = f"[FAIL] {u.full_name} ({u.id}): "
                failed_reasons = []
                
                # Check Species / Family Manually
                fam_to_user_attr = {
                    "vleermuis": "vleermuis",
                    "zwaluw": "zwaluw",
                    "zangvogel": "zangvogel",
                    "pad": "pad",
                    "langoor": "langoor",
                    "roofvogel": "roofvogel",
                }
                
                for sp in visit.species:
                    fam = sp.family
                    fam_name = (fam.name if fam else sp.name).lower().strip()
                    attr = fam_to_user_attr.get(fam_name)
                    if attr and not getattr(u, attr, False):
                        failed_reasons.append(f"Missing '{attr}' for {fam_name}")
                
                # Check VRFG
                if any("vliegroute" in (f.name or "").lower() for f in visit.functions):
                     if not u.vrfg: failed_reasons.append("Missing 'vrfg'")
                
                # Check Flags
                for flag in ["wbc", "fiets", "hub", "dvp"]:
                    if getattr(visit, flag, False) and not getattr(u, flag, False):
                        failed_reasons.append(f"Missing '{flag}'")
                        
                msg += ", ".join(failed_reasons)
                # print(msg) # Hide failures to focus on capacity? Or Keep? Keep but maybe simpler.

        print(f"\nSummary:")
        print(f"Qualified Users: {qualified_count}")
        print(f"Users with Capacity ({week_to_check}): {capacity_count}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backend/debug_planning.py <visit_id> [target_week]")
    else:
        asyncio.run(debug_visit(int(sys.argv[1])))
