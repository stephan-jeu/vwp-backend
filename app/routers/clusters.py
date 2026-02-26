from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status, Response
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.models.cluster import Cluster
from app.models.project import Project
from app.models.function import Function
from app.models.species import Species
from app.models.user import User
from app.models.visit import (
    Visit,
)
from app.schemas.cluster import (
    ClusterCreate,
    ClusterDuplicate,
    ClusterRead,
    ClusterWithVisitsRead,
    VisitReadCompact,
    ClusterVisitRow,
    ClusterUpdate,
)
from app.schemas.function import FunctionCompactRead
from app.schemas.species import SpeciesCompactRead
from app.schemas.user import UserNameRead
from app.deps import AdminDep, DbDep
from app.db.utils import select_active
from app.services.visit_generation import (
    duplicate_cluster_with_visits,
    resolve_protocols_for_combos,
    generate_visits_for_cluster,
    derive_start_time_text_for_visit,
)
from app.services.activity_log_service import log_activity
from app.services.planning_run_errors import PlanningRunError
from app.services.soft_delete import soft_delete_entity


router = APIRouter()


def _validate_planning_locked_defaults(
    *,
    default_planning_locked: bool,
    default_planned_week: int | None,
    default_researcher_ids: list[int] | None,
) -> None:
    if not default_planning_locked:
        return
    if default_planned_week is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="default_planning_locked requires default_planned_week",
        )
    if not default_researcher_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="default_planning_locked requires default_researcher_ids",
        )


@router.get("", response_model=list[ClusterWithVisitsRead])
async def list_clusters(
    _: AdminDep, db: DbDep, project_id: Annotated[int | None, Query()] = None
) -> list[ClusterWithVisitsRead]:
    """List clusters, optionally filtered by project id, including compact visits."""

    stmt: Select[tuple[Cluster]]
    if project_id is None:
        stmt = select_active(Cluster).order_by(Cluster.project_id, Cluster.cluster_number)
    else:
        stmt = (
            select_active(Cluster)
            .where(Cluster.project_id == project_id)
            .order_by(Cluster.cluster_number)
        )
    rows = (await db.execute(stmt)).scalars().all()

    # Fetch visits per cluster
    result: list[ClusterWithVisitsRead] = []
    for cluster in rows:
        visits_stmt: Select[tuple[Visit]] = (
            select_active(Visit)
            .where(Visit.cluster_id == cluster.id)
            .options(
                selectinload(Visit.functions),
                selectinload(Visit.species).selectinload(Species.family),
                selectinload(Visit.researchers),
            )
            .order_by(Visit.visit_nr)
        )
        visits = (await db.execute(visits_stmt)).scalars().all()
        result.append(
            ClusterWithVisitsRead(
                id=cluster.id,
                project_id=cluster.project_id,
                address=cluster.address,
                location=cluster.location,
                cluster_number=cluster.cluster_number,
                visits=[
                    VisitReadCompact(
                        id=v.id,
                        cluster_id=v.cluster_id,
                        function_ids=[f.id for f in v.functions],
                        species_ids=[s.id for s in v.species],
                        functions=[
                            FunctionCompactRead(id=f.id, name=f.name)
                            for f in v.functions
                        ],
                        species=[
                            SpeciesCompactRead.model_validate(s) for s in v.species
                        ],
                        part_of_day=v.part_of_day,
                        start_time_text=(
                            v.start_time_text
                            or derive_start_time_text_for_visit(v.part_of_day, None)
                        ),
                        group_id=v.group_id,
                        required_researchers=v.required_researchers,
                        visit_nr=v.visit_nr,
                        from_date=v.from_date,
                        to_date=v.to_date,
                        duration=v.duration,
                        min_temperature_celsius=v.min_temperature_celsius,
                        max_wind_force_bft=v.max_wind_force_bft,
                        max_precipitation=v.max_precipitation,
                        expertise_level=v.expertise_level,
                        wbc=v.wbc,
                        fiets=v.fiets,
                        vog=v.vog,
                        hub=v.hub,
                        dvp=v.dvp,
                        sleutel=v.sleutel,
                        remarks_planning=v.remarks_planning,
                        remarks_field=v.remarks_field,
                        priority=v.priority,
                        planned_week=v.planned_week,
                        planning_locked=v.planning_locked,
                        researcher_ids=[u.id for u in (v.researchers or [])],
                        researchers=[
                            UserNameRead(id=u.id, full_name=u.full_name)
                            for u in (v.researchers or [])
                        ],
                    )
                    for v in visits
                ],
            )
        )
    return result


@router.get("/flat", response_model=list[ClusterVisitRow])
async def list_clusters_flat(
    _: AdminDep, db: DbDep, project_id: Annotated[int | None, Query()] = None
) -> list[ClusterVisitRow]:
    """Return a flattened list of rows combining cluster and visit data.

    This is optimized for grouped table rendering in the frontend where each
    row is a visit augmented with cluster grouping metadata.
    """

    stmt: Select[tuple[Cluster]]
    if project_id is None:
        stmt = select_active(Cluster).order_by(Cluster.project_id, Cluster.cluster_number)
    else:
        stmt = (
            select_active(Cluster)
            .where(Cluster.project_id == project_id)
            .order_by(Cluster.cluster_number)
        )
    clusters = (await db.execute(stmt)).scalars().all()

    rows: list[ClusterVisitRow] = []
    for cluster in clusters:
        visits_stmt: Select[tuple[Visit]] = (
            select_active(Visit)
            .where(Visit.cluster_id == cluster.id)
            .options(
                selectinload(Visit.functions),
                selectinload(Visit.species).selectinload(Species.family),
            )
            .order_by(Visit.visit_nr)
        )
        visits = (await db.execute(visits_stmt)).scalars().all()
        for v in visits:
            if not getattr(v, "start_time_text", None):
                setattr(
                    v,
                    "start_time_text",
                    derive_start_time_text_for_visit(v.part_of_day, None),
                )
            rows.append(
                ClusterVisitRow(
                    id=v.id,
                    cluster_id=cluster.id,
                    cluster_number=cluster.cluster_number,
                    cluster_address=cluster.address,
                    function_ids=[f.id for f in v.functions],
                    functions=[
                        FunctionCompactRead(id=f.id, name=f.name) for f in v.functions
                    ],
                    species_ids=[s.id for s in v.species],
                    species=[SpeciesCompactRead.model_validate(s) for s in v.species],
                    required_researchers=v.required_researchers,
                    visit_nr=v.visit_nr,
                    from_date=v.from_date,
                    to_date=v.to_date,
                    duration=v.duration,
                    min_temperature_celsius=v.min_temperature_celsius,
                    max_wind_force_bft=v.max_wind_force_bft,
                    max_precipitation=v.max_precipitation,
                    expertise_level=v.expertise_level,
                    wbc=v.wbc,
                    fiets=v.fiets,
                    vog=v.vog,
                    hub=v.hub,
                    dvp=v.dvp,
                    sleutel=v.sleutel,
                    remarks_planning=v.remarks_planning,
                    remarks_field=v.remarks_field,
                    start_time_text=v.start_time_text,
                )
            )
    return rows


@router.post(
    "", response_model=ClusterWithVisitsRead, status_code=status.HTTP_201_CREATED
)
async def create_cluster(
    admin: AdminDep, db: DbDep, payload: ClusterCreate
) -> ClusterWithVisitsRead:
    """Create cluster and append generated visits based on selected functions/species."""

    _validate_planning_locked_defaults(
        default_planning_locked=payload.default_planning_locked,
        default_planned_week=payload.default_planned_week,
        default_researcher_ids=payload.default_researcher_ids,
    )

    # If a cluster with the same project and number exists, merge by appending visits
    existing_stmt: Select[tuple[Cluster]] = (
        select_active(Cluster)
        .where(
            (Cluster.project_id == payload.project_id)
            & (Cluster.cluster_number == payload.cluster_number)
        )
        .limit(1)
    )
    existing = (await db.execute(existing_stmt)).scalars().first()
    if existing is not None:
        # Update address and location as requested, keep the same cluster row
        existing.address = payload.address
        existing.location = payload.location
        cluster = existing
    else:
        cluster = Cluster(
            project_id=payload.project_id,
            address=payload.address,
            location=payload.location,
            cluster_number=payload.cluster_number,
        )
        db.add(cluster)
        await db.flush()

    warnings: list[str] = []
    _visits_created_ids: list[int] = []
    try:
        if payload.combos:
            combos_dicts = [
                {"function_ids": c.function_ids, "species_ids": c.species_ids}
                for c in payload.combos
            ]
            protocols = await resolve_protocols_for_combos(db=db, combos=combos_dicts)
            visits_created, warnings = await generate_visits_for_cluster(
                db=db,
                cluster=cluster,
                function_ids=[],
                species_ids=[],
                protocols=protocols,
                default_required_researchers=payload.default_required_researchers,
                default_planned_week=payload.default_planned_week,
                default_researcher_ids=payload.default_researcher_ids,
                default_planning_locked=payload.default_planning_locked,
                default_expertise_level=payload.default_expertise_level,
                default_wbc=payload.default_wbc,
                default_fiets=payload.default_fiets,
                default_vog=payload.default_vog,
                default_hub=payload.default_hub,
                default_dvp=payload.default_dvp,
                default_sleutel=payload.default_sleutel,
                default_remarks_field=payload.default_remarks_field,
            )
            _visits_created_ids = [v.id for v in visits_created]

        await db.commit()
        await db.refresh(cluster)
    except PlanningRunError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Het is niet gelukt om de SFC's goed te combineren. "
                "Probeer het nog een keer of pas de bezoeken handmatig aan."
            ),
        ) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Het is niet gelukt om de SFC's goed te combineren. "
                "Probeer het nog een keer of pas de bezoeken handmatig aan."
            ),
        ) from exc

    # Re-query visits for response
    visits_stmt: Select[tuple[Visit]] = (
        select_active(Visit)
        .where(Visit.cluster_id == cluster.id)
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
        )
    )
    visits = (await db.execute(visits_stmt)).scalars().all()
    response = ClusterWithVisitsRead(
        id=cluster.id,
        project_id=cluster.project_id,
        address=cluster.address,
        location=cluster.location,
        cluster_number=cluster.cluster_number,
        visits=[
            VisitReadCompact(
                id=v.id,
                cluster_id=v.cluster_id,
                function_ids=[f.id for f in v.functions],
                species_ids=[s.id for s in v.species],
                functions=[
                    FunctionCompactRead(id=f.id, name=f.name) for f in v.functions
                ],
                species=[SpeciesCompactRead.model_validate(s) for s in v.species],
                part_of_day=v.part_of_day,
                start_time_text=(
                    v.start_time_text
                    or derive_start_time_text_for_visit(v.part_of_day, None)
                ),
                group_id=v.group_id,
                required_researchers=v.required_researchers,
                visit_nr=v.visit_nr,
                from_date=v.from_date,
                to_date=v.to_date,
                duration=v.duration,
                min_temperature_celsius=v.min_temperature_celsius,
                max_wind_force_bft=v.max_wind_force_bft,
                max_precipitation=v.max_precipitation,
                expertise_level=v.expertise_level,
                wbc=v.wbc,
                fiets=v.fiets,
                vog=v.vog,
                hub=v.hub,
                dvp=v.dvp,
                sleutel=v.sleutel,
                remarks_planning=v.remarks_planning,
                remarks_field=v.remarks_field,
                priority=v.priority,
                planned_week=v.planned_week,
                planning_locked=v.planning_locked,
                researcher_ids=[u.id for u in (v.researchers or [])],
                researchers=[
                    UserNameRead(id=u.id, full_name=u.full_name)
                    for u in (v.researchers or [])
                ],
            )
            for v in visits
        ],
        warnings=warnings,
    )

    # Log cluster creation including high-level function/species context
    project_code: str | None = None
    if cluster.project_id is not None:
        project_stmt: Select[tuple[Project]] = select_active(Project).where(
            Project.id == cluster.project_id
        )
        project = (await db.execute(project_stmt)).scalars().first()
        if project is not None:
            project_code = getattr(project, "code", None)

    function_ids: set[int] = set()
    species_ids: set[int] = set()
    for combo in payload.combos or []:
        function_ids.update(combo.function_ids)
        species_ids.update(combo.species_ids)

    function_names: list[str] = []
    species_abbreviations: list[str] = []

    if function_ids:
        func_stmt: Select[tuple[Function]] = select(Function).where(
            Function.id.in_(sorted(function_ids))
        )
        funcs = (await db.execute(func_stmt)).scalars().all()
        function_names = [f.name or "" for f in funcs if getattr(f, "name", None)]

    if species_ids:
        species_stmt: Select[tuple[Species]] = select(Species).where(
            Species.id.in_(sorted(species_ids))
        )
        species_rows = (await db.execute(species_stmt)).scalars().all()
        for s in species_rows:
            label = getattr(s, "abbreviation", None) or getattr(s, "name", None)
            if label:
                species_abbreviations.append(label)

    await log_activity(
        db,
        actor_id=admin.id,
        action="cluster_created",
        target_type="cluster",
        target_id=cluster.id,
        details={
            "project_id": cluster.project_id,
            "project_code": project_code,
            "cluster_number": cluster.cluster_number,
            "address": cluster.address,
            "function_ids": sorted(function_ids),
            "species_ids": sorted(species_ids),
            "function_names": function_names,
            "species_abbreviations": species_abbreviations,
        },
    )

    return response


@router.post("/{cluster_id}/duplicate", response_model=ClusterRead)
async def duplicate_cluster(
    admin: AdminDep, db: DbDep, cluster_id: int, payload: ClusterDuplicate
) -> ClusterRead:
    """Duplicate cluster including its visits into a new cluster row."""

    source = await db.get(Cluster, cluster_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    new_cluster = await duplicate_cluster_with_visits(
        db=db,
        source_cluster=source,
        new_number=payload.cluster_number,
        new_address=payload.address,
        new_location=payload.location,
    )
    await db.commit()
    await db.refresh(new_cluster)

    # Eager load visits with relations to populate log details
    visits_stmt: Select[tuple[Visit]] = (
        select_active(Visit)
        .where(Visit.cluster_id == new_cluster.id)
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
        )
    )
    new_visits = (await db.execute(visits_stmt)).scalars().all()

    # Resolve project code
    project_code: str | None = None
    if new_cluster.project_id is not None:
        project = await db.get(Project, new_cluster.project_id)
        if project:
            project_code = getattr(project, "code", None)

    # Collect distinct function names and species abbreviations
    unique_func_names = set()
    unique_species_abbrs = set()
    for v in new_visits:
        for f in v.functions:
            if f.name:
                unique_func_names.add(f.name)
        for s in v.species:
            label = s.abbreviation or s.name
            if label:
                unique_species_abbrs.add(label)

    await log_activity(
        db,
        actor_id=admin.id,
        action="cluster_duplicated",
        target_type="cluster",
        target_id=new_cluster.id,
        details={
            "source_cluster_id": source.id,
            "project_id": new_cluster.project_id,
            "project_code": project_code,
            "cluster_number": new_cluster.cluster_number,
            "address": new_cluster.address,
            "visits_created": [v.id for v in new_visits],
            "visit_count": len(new_visits),
            "function_names": sorted(unique_func_names),
            "species_abbreviations": sorted(unique_species_abbrs),
        },
    )

    return ClusterRead(
        id=new_cluster.id,
        project_id=new_cluster.project_id,
        address=new_cluster.address,
        location=new_cluster.location,
        cluster_number=new_cluster.cluster_number,
    )


@router.patch("/{cluster_id}", response_model=ClusterRead)
async def update_cluster(
    admin: AdminDep, db: DbDep, cluster_id: int, payload: ClusterUpdate
) -> ClusterRead:
    """Update mutable fields on a cluster (address, location, cluster_number)."""

    cluster = await db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    cluster.address = payload.address
    cluster.location = payload.location
    cluster.cluster_number = payload.cluster_number
    await db.commit()
    await db.refresh(cluster)

    project_code: str | None = None
    if cluster.project_id is not None:
        project = await db.get(Project, cluster.project_id)
        if project:
            project_code = getattr(project, "code", None)

    await log_activity(
        db,
        actor_id=admin.id,
        action="cluster_updated",
        target_type="cluster",
        target_id=cluster.id,
        details={
            "project_id": cluster.project_id,
            "project_code": project_code,
            "cluster_number": cluster.cluster_number,
            "address": cluster.address,
        },
    )

    return ClusterRead(
        id=cluster.id,
        project_id=cluster.project_id,
        address=cluster.address,
        location=cluster.location,
        cluster_number=cluster.cluster_number,
    )


@router.delete(
    "/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_cluster(admin: AdminDep, db: DbDep, cluster_id: int) -> Response:
    """Soft-delete a cluster by id; cascade to visits."""

    cluster = await db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await soft_delete_entity(db, cluster, cascade=True)
    await db.commit()

    project_code: str | None = None
    project_id = getattr(cluster, "project_id", None)
    if project_id is not None:
        stmt: Select[tuple[Project]] = select_active(Project).where(Project.id == project_id)
        project = (await db.execute(stmt)).scalars().first()
        if project is not None:
            project_code = getattr(project, "code", None)

    await log_activity(
        db,
        actor_id=admin.id,
        action="cluster_deleted",
        target_type="cluster",
        target_id=cluster_id,
        details={
            "project_id": getattr(cluster, "project_id", None),
            "cluster_number": getattr(cluster, "cluster_number", None),
            "address": getattr(cluster, "address", None),
            "project_code": project_code,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
