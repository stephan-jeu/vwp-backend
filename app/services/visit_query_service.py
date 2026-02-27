from datetime import date
from typing import Optional

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.db.utils import select_active
from app.models.cluster import Cluster
from app.models.function import Function
from app.models.project import Project
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.species import Species
from app.models.user import User
from app.models.visit import (
    Visit,
    visit_functions,
    visit_researchers,
    visit_species,
)
from app.services.visit_status_service import VisitStatusCode


def apply_visit_filters(
    stmt: Select,
    *,
    search: Optional[str] = None,
    week: Optional[int] = None,
    cluster_number: Optional[str] = None,
    function_ids: Optional[list[int]] = None,
    species_ids: Optional[list[int]] = None,
    unplanned_only: bool = False,
) -> Select:
    """Apply standard filters to a Visit select statement."""

    # --- Week Filtering ---
    if week is not None:
        stmt = stmt.where(
            or_(
                Visit.planned_week == week,
                and_(
                    Visit.planned_week.is_(None),
                    Visit.provisional_week == week,
                ),
            )
        )

    if unplanned_only:
        stmt = stmt.where(
            Visit.provisional_week.is_(None), Visit.planned_week.is_(None)
        )

    if cluster_number is not None:
        stmt = stmt.where(Cluster.cluster_number == cluster_number)

    joined_functions = False
    joined_species = False
    if function_ids:
        stmt = stmt.join(visit_functions, Visit.id == visit_functions.c.visit_id)
        stmt = stmt.where(visit_functions.c.function_id.in_(function_ids))
        joined_functions = True

    if species_ids:
        stmt = stmt.join(visit_species, Visit.id == visit_species.c.visit_id)
        stmt = stmt.where(visit_species.c.species_id.in_(species_ids))
        joined_species = True

    # Optional text search across project, cluster and related names
    if search:
        term = search.strip().lower()
        like = f"%{term}%"
        if not joined_functions:
            stmt = stmt.outerjoin(
                visit_functions, Visit.id == visit_functions.c.visit_id
            )
        stmt = stmt.outerjoin(Function, Function.id == visit_functions.c.function_id)
        if not joined_species:
            stmt = stmt.outerjoin(visit_species, Visit.id == visit_species.c.visit_id)
        stmt = stmt.outerjoin(Species, Species.id == visit_species.c.species_id)
        stmt = stmt.outerjoin(
            visit_researchers, Visit.id == visit_researchers.c.visit_id
        )
        stmt = stmt.outerjoin(User, User.id == visit_researchers.c.user_id)

        stmt = stmt.where(
            or_(
                func.lower(Project.code).like(like),
                func.lower(Project.location).like(like),
                func.lower(Cluster.address).like(like),
                Cluster.cluster_number.like(like),
                func.lower(Function.name).like(like),
                func.lower(Species.name).like(like),
                func.lower(Species.abbreviation).like(like),
                func.lower(User.full_name).like(like),
                func.lower(Visit.custom_function_name).like(like),
                func.lower(Visit.custom_species_name).like(like),
            )
        )

    return stmt


def get_visit_selection_stmt() -> Select:
    """Return the base select statement for visits with standard joins."""
    stmt = (
        select(Visit.id)
        .join(Cluster, Visit.cluster_id == Cluster.id)
        .join(Project, Cluster.project_id == Project.id, isouter=True)
    )
    stmt = stmt.where(or_(Project.quote.is_(False), Project.quote.is_(None)))
    stmt = stmt.where(Visit.deleted_at.is_(None))
    return stmt


def get_visit_loading_stmt(visit_ids: list[int], include_archived: bool = False) -> Select:
    """Return the statement to load full visit objects for given IDs."""
    return (
        select_active(Visit, include_archived=include_archived)
        .where(Visit.id.in_(visit_ids))
        .options(
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
            selectinload(Visit.protocol_visit_windows).selectinload(
                ProtocolVisitWindow.protocol
            ),
        )
    )
