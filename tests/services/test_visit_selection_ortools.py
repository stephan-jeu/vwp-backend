from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from typing import Any

import pytest

from app.services.visit_selection_ortools import select_visits_cp_sat


def make_species(family_name: str) -> Any:
    """Create a simple species mock with a family name.

    Args:
        family_name: Species family name.

    Returns:
        SimpleNamespace representing the species.
    """

    family = SimpleNamespace(name=family_name)
    return SimpleNamespace(family=family, name=family_name)


def make_visit(*, vid: int, family_name: str, required_researchers: int) -> Any:
    """Create a minimal visit object for CP-SAT tests.

    Args:
        vid: Visit id.
        family_name: Species family name.
        required_researchers: Number of required researchers.

    Returns:
        SimpleNamespace representing the visit.
    """

    protocol = SimpleNamespace(protocol_id=vid, visit_index=1)
    visit = MagicMock()
    visit.id = vid
    visit.part_of_day = "Ochtend"
    visit.from_date = date(2026, 5, 1)
    visit.to_date = date(2026, 5, 10)
    visit.required_researchers = required_researchers
    visit.functions = [SimpleNamespace(name="Inventarisatie")]
    visit.species = [make_species(family_name)]
    visit.protocol_visit_windows = [protocol]
    visit.provisional_week = None
    visit.provisional_locked = False
    visit.hub = False
    visit.fiets = False
    visit.dvp = False
    visit.wbc = False
    visit.sleutel = False
    visit.expertise_level = None
    visit.priority = False
    return visit


def make_user(*, uid: int, contract: str, experience_bat: str, family_flag: str) -> Any:
    """Create a minimal user object for CP-SAT tests.

    Args:
        uid: User id.
        contract: Contract label.
        experience_bat: Bat experience label.
        family_flag: Family attribute to set to True.

    Returns:
        SimpleNamespace representing the user.
    """

    defaults = {
        "smp_huismus": False,
        "smp_vleermuis": False,
        "smp_gierzwaluw": False,
        "vrfg": False,
        "hub": False,
        "fiets": False,
        "wbc": False,
        "dvp": False,
        "sleutel": False,
        "pad": False,
        "langoor": False,
        "roofvogel": False,
        "vleermuis": False,
        "zwaluw": False,
        "vlinder": False,
        "teunisbloempijlstaart": False,
        "zangvogel": False,
        "biggenkruid": False,
        "schijfhoren": False,
    }
    defaults[family_flag] = True
    user = MagicMock()
    user.id = uid
    user.contract = contract
    user.contract_type = contract
    user.experience_bat = experience_bat
    user.full_name = f"U{uid}"
    for key, value in defaults.items():
        setattr(user, key, value)
    return user


@pytest.mark.asyncio
async def test_cp_sat_prefers_supervisor_for_vleermuis_multi_person():
    """Ensure Vleermuis multi-person visits prefer a supervisor mix.

    Returns:
        None.
    """

    # Arrange
    visit = make_visit(vid=1, family_name="Vleermuis", required_researchers=2)
    users = [
        make_user(
            uid=1, contract="Flex", experience_bat="Junior", family_flag="vleermuis"
        ),
        make_user(
            uid=2, contract="Flex", experience_bat="Junior", family_flag="vleermuis"
        ),
        make_user(
            uid=3, contract="Fixed", experience_bat="Medior", family_flag="vleermuis"
        ),
    ]
    user_caps = {1: 1, 2: 1, 3: 1}
    user_daypart_caps = {
        1: {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0},
        2: {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0},
        3: {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0},
    }

    # Act
    result = await select_visits_cp_sat(
        db=[],
        week_monday=date(2026, 5, 4),
        visits=[visit],
        users=users,
        user_caps=user_caps,
        user_daypart_caps=user_daypart_caps,
        include_travel_time=False,
        today=date(2026, 5, 4),
    )

    # Assert
    assert result.selected == [visit]
    assigned = getattr(visit, "researchers", [])
    assert any(getattr(u, "experience_bat", "") == "Medior" for u in assigned)


@pytest.mark.asyncio
async def test_cp_sat_allows_non_vleermuis_without_supervisor():
    """Ensure non-Vleermuis visits can be staffed by juniors only.

    Returns:
        None.
    """

    # Arrange
    visit = make_visit(vid=2, family_name="Zwaluw", required_researchers=2)
    users = [
        make_user(
            uid=1, contract="Flex", experience_bat="Junior", family_flag="zwaluw"
        ),
        make_user(
            uid=2, contract="Flex", experience_bat="Junior", family_flag="zwaluw"
        ),
    ]
    user_caps = {1: 1, 2: 1}
    user_daypart_caps = {
        1: {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0},
        2: {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0},
    }

    # Act
    result = await select_visits_cp_sat(
        db=[],
        week_monday=date(2026, 5, 4),
        visits=[visit],
        users=users,
        user_caps=user_caps,
        user_daypart_caps=user_daypart_caps,
        include_travel_time=False,
        today=date(2026, 5, 4),
    )

    # Assert
    assert result.selected == [visit]
    assigned = getattr(visit, "researchers", [])
    assert len(assigned) == 2


@pytest.mark.asyncio
async def test_cp_sat_allows_single_researcher_vleermuis_junior_only():
    """Ensure single-researcher Vleermuis visits can be junior-only.

    Returns:
        None.
    """

    # Arrange
    visit = make_visit(vid=3, family_name="Vleermuis", required_researchers=1)
    users = [
        make_user(
            uid=1, contract="Flex", experience_bat="Junior", family_flag="vleermuis"
        ),
    ]
    user_caps = {1: 1}
    user_daypart_caps = {
        1: {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0},
    }

    # Act
    result = await select_visits_cp_sat(
        db=[],
        week_monday=date(2026, 5, 4),
        visits=[visit],
        users=users,
        user_caps=user_caps,
        user_daypart_caps=user_daypart_caps,
        include_travel_time=False,
        today=date(2026, 5, 4),
    )

    # Assert
    assert result.selected == [visit]
    assigned = getattr(visit, "researchers", [])
    assert len(assigned) == 1
    assert assigned[0].experience_bat == "Junior"


@pytest.mark.asyncio
async def test_cp_sat_enforces_dutch_buddy_for_english(monkeypatch):
    """Ensure English speakers are paired with Dutch speakers when constraint is enabled.
    
    Returns:
        None.
    """
    # Enable constraint
    monkeypatch.setenv("CONSTRAINT_ENGLISH_DUTCH_TEAMING", "true")
    from core.settings import get_settings
    # Force reload settings to pick up env var
    get_settings().constraint_english_dutch_teaming = True

    # Arrange
    # Visit requires 2 people
    visit = make_visit(vid=4, family_name="Vleermuis", required_researchers=2)
    
    # Users:
    # 1. EN
    # 2. EN
    # 3. NL
    users = [
        make_user(uid=1, contract="Flex", experience_bat="Medior", family_flag="vleermuis"),
        make_user(uid=2, contract="Flex", experience_bat="Medior", family_flag="vleermuis"),
        make_user(uid=3, contract="Flex", experience_bat="Medior", family_flag="vleermuis"),
    ]
    users[0].language = "EN"
    users[1].language = "EN"
    users[2].language = "NL"
    
    # Caps to allow all
    user_caps = {1: 1, 2: 1, 3: 1}
    user_daypart_caps = {u.id: {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0} for u in users}

    # Act
    # Using existing function
    result = await select_visits_cp_sat(
        db=[],
        week_monday=date(2026, 5, 4),
        visits=[visit],
        users=users,
        user_caps=user_caps,
        user_daypart_caps=user_daypart_caps,
        include_travel_time=False,
        today=date(2026, 5, 4),
    )
    
    # Assert
    # Selected team should be [EN, NL] or [NL, EN] to avoid penalty
    # [EN, EN] incurs penalty logic
    # Wait, simple test: 
    # If [EN, EN] -> Penalty. If [EN, NL] -> No Penalty.
    # Solver maximizes objective. 
    # With only 1 visit and enough capacity, it should pick the team that maximizes score (minimizes penalty).
    # [EN, EN] -> Penalty=50.
    # [EN, NL] -> Penalty=0.
    # So it MUST pick [EN, NL].
    
    assert result.selected == [visit]
    assigned = getattr(visit, "researchers", [])
    assert len(assigned) == 2
    
    # Check languages
    langs = [getattr(u, "language", "NL") for u in assigned]
    assert "NL" in langs, f"Expected at least one NL speaker, got {langs}"


@pytest.mark.asyncio
async def test_cp_sat_ignores_language_when_disabled(monkeypatch):
    """Ensure language constraint is ignored when disabled.
    
    Returns:
        None.
    """
    # Disable constraint
    monkeypatch.setenv("CONSTRAINT_ENGLISH_DUTCH_TEAMING", "false")
    from core.settings import get_settings
    get_settings().constraint_english_dutch_teaming = False

    # Arrange
    # Visit requires 2 people
    visit = make_visit(vid=5, family_name="Vleermuis", required_researchers=2)
    
    # Users:
    # 1. EN
    # 2. EN
    # 3. NL (but make NL unavailable/less preferred to test preference?)
    # Actually, if disabled, [EN, EN] is valid and has NO penalty.
    # To prove it ignores, we need a setup where [EN, EN] is preferred for other reasons (e.g. travel time, or list order luck).
    # OR we just check that [EN, EN] is *allowed*.
    
    users = [
        make_user(uid=1, contract="Flex", experience_bat="Medior", family_flag="vleermuis"),
        make_user(uid=2, contract="Flex", experience_bat="Medior", family_flag="vleermuis"),
    ]
    users[0].language = "EN"
    users[1].language = "EN"
    
    user_caps = {1: 1, 2: 1}
    user_daypart_caps = {u.id: {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0} for u in users}

    # Act
    result = await select_visits_cp_sat(
        db=[],
        week_monday=date(2026, 5, 4),
        visits=[visit],
        users=users,
        user_caps=user_caps,
        user_daypart_caps=user_daypart_caps,
        include_travel_time=False,
        today=date(2026, 5, 4),
    )
    
    # Assert
    # Should schedule even though it's [EN, EN]
    assert result.selected == [visit]
    assigned = getattr(visit, "researchers", [])
    assert len(assigned) == 2
    langs = [getattr(u, "language", "NL") for u in assigned]
    assert langs == ["EN", "EN"]
