
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch
import pytest

from app.services.visit_selection_ortools import select_visits_cp_sat
import app.services.travel_time # Ensure module is loaded for patching
import app.services.visit_planning_selection # Ensure module is loaded for patching
from app.models.visit import Visit
from app.models.user import User
from app.models.cluster import Cluster
from app.models.project import Project

# --- Helpers ---

def make_visit(vid: int, required_researchers: int = 1) -> Visit:
    v = MagicMock(spec=Visit)
    v.id = vid
    v.required_researchers = required_researchers
    v.part_of_day = "Ochtend"
    v.from_date = date(2026, 5, 1)
    v.to_date = date(2026, 5, 10)
    v.protocol_visit_windows = []
    v.provisional_week = None
    v.provisional_locked = False
    v.priority = False
    
    # Needs a cluster with address for travel time check
    cluster = MagicMock(spec=Cluster)
    cluster.address = "VisitLocation"
    cluster.project = MagicMock(spec=Project)
    cluster.project.location = "ProjectLoc"
    v.cluster = cluster
    
    # Mock species to avoid errors
    v.species = []
    
    return v

def make_user(uid: int) -> User:
    u = MagicMock(spec=User)
    u.id = uid
    u.address = "UserLocation"
    # Basic caps to ensure they can be picked
    u.smp_vleermuis = True # generic skill
    return u

@pytest.mark.asyncio
async def test_max_travel_time_configuration():
    """Verify that the max travel time constraint respects the settings configuration."""
    
    # Arrange
    visit = make_visit(vid=100, required_researchers=1)
    # We need to make sure the user qualifies. 
    # The visit needs a skill. Let's say we mock _qualifies_user_for_visit to True
    
    user = make_user(uid=10)
    
    users = [user]
    user_caps = {10: 5}
    user_daypart_caps = {10: {"Ochtend": 1, "Dag": 1, "Avond": 1, "Flex": 1}}
    
    # Mock dependencies
    # 1. travel_time service: return 70 minutes
    # 2. get_settings: return limit 60 (Strict) vs 80 (Loose)
    # 3. _qualifies_user_for_visit: Always True
    
    with patch("app.services.travel_time.get_travel_minutes_batch") as mock_get_travel, \
         patch("app.services.visit_selection_ortools.get_settings") as mock_settings_getter, \
         patch("app.services.visit_planning_selection._qualifies_user_for_visit", return_value=True):
         
        # Setup Travel Time Mock
        mock_get_travel.return_value = {("UserLocation", "VisitLocation, ProjectLoc"): 70}
        
        # --- CASE 1: Strict Limit (60 mins) < Travel (70 mins) ---
        # User should NOT be assigned
        mock_settings = MagicMock()
        mock_settings.constraint_max_travel_time_minutes = 60
        # Ensure other settings don't crash
        mock_settings.constraint_large_team_penalty = True
        mock_settings_getter.return_value = mock_settings
        
        result_strict = await select_visits_cp_sat(
            db=[],
            week_monday=date(2026, 5, 4),
            visits=[visit],
            users=users,
            user_caps=user_caps,
            user_daypart_caps=user_daypart_caps,
            include_travel_time=True
        )
        
        # Expectation: Visit NOT scheduled or User NOT assigned
        # Since only 1 user and they are blocked by travel, visit should be unscheduled
        assert visit not in result_strict.selected, "Visit should be skipped due to strict travel limit"
        
        # --- CASE 2: Loose Limit (80 mins) > Travel (70 mins) ---
        # User SHOULD be assigned
        mock_settings.constraint_max_travel_time_minutes = 80
        
        result_loose = await select_visits_cp_sat(
            db=[],
            week_monday=date(2026, 5, 4),
            visits=[visit],
            users=users,
            user_caps=user_caps,
            user_daypart_caps=user_daypart_caps,
            include_travel_time=True
        )
        
        # Expectation: Visit Scheduled
        assert visit in result_loose.selected, "Visit should be scheduled with loose travel limit"
        assert len(getattr(visit, "researchers", [])) == 1

@pytest.mark.asyncio
async def test_consecutive_travel_penalty():
    """Verify that the model favors closer clusters for consecutive visits."""
    
    # Arrange 2 morning visits and 1 daytime visit
    # Visit 1 (Morning, Cluster A)
    v1 = make_visit(vid=101)
    v1.part_of_day = "Ochtend"
    v1.cluster.address = "CloseLocal"
    
    # Visit 2 (Morning, Cluster B)
    v2 = make_visit(vid=102)
    v2.part_of_day = "Ochtend"
    v2.cluster.address = "FarLocal"
    
    # Visit 3 (Day, Cluster C)
    v3 = make_visit(vid=103)
    v3.part_of_day = "Dag"
    v3.cluster.address = "TargetLocal"
    
    user = make_user(uid=11)
    users = [user]
    # Give user enough capacity to do 1 Morning and 1 Day
    user_caps = {11: 5}
    user_daypart_caps = {11: {"Ochtend": 1, "Dag": 1, "Avond": 0, "Flex": 0}}
    
    # We set it up such that:
    # TargetLocal to CloseLocal is 5 mins
    # TargetLocal to FarLocal is 25 mins
    # Both are within the 30 min hard limit, but CloseLocal is cheaper because of the penalty.
    
    with patch("app.services.travel_time.get_travel_minutes_batch") as mock_get_travel, \
         patch("app.services.visit_selection_ortools.get_settings") as mock_settings_getter, \
         patch("app.services.visit_planning_selection._qualifies_user_for_visit", return_value=True):
         
        mock_get_travel.return_value = {
            ("UserLocation", "CloseLocal, ProjectLoc"): 10,
            ("UserLocation", "FarLocal, ProjectLoc"): 10,
            ("UserLocation", "TargetLocal, ProjectLoc"): 15,
            ("CloseLocal, ProjectLoc", "TargetLocal, ProjectLoc"): 5,
            ("FarLocal, ProjectLoc", "TargetLocal, ProjectLoc"): 25,
            ("TargetLocal, ProjectLoc", "CloseLocal, ProjectLoc"): 5,
            ("TargetLocal, ProjectLoc", "FarLocal, ProjectLoc"): 25
        }
        
        mock_settings = MagicMock()
        mock_settings.feature_strict_availability = True
        mock_settings.constraint_consecutive_travel_penalty = True
        mock_settings.constraint_consecutive_travel_penalty_weight = 10
        mock_settings.constraint_max_travel_time_minutes = 60
        mock_settings.constraint_large_team_penalty = True
        mock_settings_getter.return_value = mock_settings
        
        result = await select_visits_cp_sat(
            db=[],
            week_monday=date(2026, 5, 4),
            visits=[v1, v2, v3],
            users=users,
            user_caps=user_caps,
            user_daypart_caps=user_daypart_caps,
            include_travel_time=True
        )
        
        # Expectation: User should do v1 and v3, because v1 is closer to v3 than v2.
        # But wait, priorities might override. Let's make sure priority keys don't strictly enforce v2 over v1.
        # The priorities are identical for v1 and v2, but v1 has shorter travel time penalty.
        selected_ids = {v.id for v in result.selected}
        
        assert 103 in selected_ids, "Daytime visit must be scheduled"
        assert 101 in selected_ids, "Closer morning visit should be selected"
        assert 102 not in selected_ids, "Further morning visit should NOT be selected"
