from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy import Select, select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster
from app.models.visit import (
    Visit,
    visit_functions,
    visit_species,
    visit_researchers,
)
from app.schemas.cluster import (
    ClusterCreate,
    ClusterDuplicate,
    ClusterRead,
    ClusterWithVisitsRead,
    VisitReadCompact,
    ClusterVisitRow,
)
from app.schemas.function import FunctionCompactRead
from app.schemas.species import SpeciesCompactRead
from app.services.security import require_admin
from app.services.visit_generation import (
    duplicate_cluster_with_visits,
    generate_visits_for_cluster,
    derive_start_time_text_for_visit,
)
from db.session import get_db


router = APIRouter()


DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[object, Depends(require_admin)]


@router.get("", response_model=list[ClusterWithVisitsRead])
async def list_clusters(
    _: AdminDep, db: DbDep, project_id: Annotated[int | None, Query()] = None
) -> list[ClusterWithVisitsRead]:
    """List clusters, optionally filtered by project id, including compact visits."""

    stmt: Select[tuple[Cluster]]
    if project_id is None:
        stmt = select(Cluster).order_by(Cluster.project_id, Cluster.cluster_number)
    else:
        stmt = (
            select(Cluster)
            .where(Cluster.project_id == project_id)
            .order_by(Cluster.cluster_number)
        )
    rows = (await db.execute(stmt)).scalars().all()

    # Fetch visits per cluster
    result: list[ClusterWithVisitsRead] = []
    for cluster in rows:
        visits_stmt: Select[tuple[Visit]] = (
            select(Visit)
            .where(Visit.cluster_id == cluster.id)
            .options(selectinload(Visit.functions), selectinload(Visit.species))
            .order_by(Visit.visit_nr)
        )
        visits = (await db.execute(visits_stmt)).scalars().all()
        result.append(
            ClusterWithVisitsRead(
                id=cluster.id,
                project_id=cluster.project_id,
                address=cluster.address,
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
                            SpeciesCompactRead(
                                id=s.id, name=s.name, abbreviation=s.abbreviation
                            )
                            for s in v.species
                        ],
                        part_of_day=v.part_of_day,
                        start_time=v.start_time,
                        start_time_text=(
                            v.start_time_text
                            or derive_start_time_text_for_visit(
                                v.part_of_day, v.start_time
                            )
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
                        hup=v.hup,
                        dvp=v.dvp,
                        remarks_planning=v.remarks_planning,
                        remarks_field=v.remarks_field,
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
        stmt = select(Cluster).order_by(Cluster.project_id, Cluster.cluster_number)
    else:
        stmt = (
            select(Cluster)
            .where(Cluster.project_id == project_id)
            .order_by(Cluster.cluster_number)
        )
    clusters = (await db.execute(stmt)).scalars().all()

    rows: list[ClusterVisitRow] = []
    for cluster in clusters:
        visits_stmt: Select[tuple[Visit]] = (
            select(Visit)
            .where(Visit.cluster_id == cluster.id)
            .options(selectinload(Visit.functions), selectinload(Visit.species))
            .order_by(Visit.visit_nr)
        )
        visits = (await db.execute(visits_stmt)).scalars().all()
        for v in visits:
            if not getattr(v, "start_time_text", None):
                setattr(
                    v,
                    "start_time_text",
                    derive_start_time_text_for_visit(v.part_of_day, v.start_time),
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
                    species=[
                        SpeciesCompactRead(
                            id=s.id, name=s.name, abbreviation=s.abbreviation
                        )
                        for s in v.species
                    ],
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
                    hup=v.hup,
                    dvp=v.dvp,
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
    _: AdminDep, db: DbDep, payload: ClusterCreate
) -> ClusterWithVisitsRead:
    """Create cluster and append generated visits based on selected functions/species."""

    cluster = Cluster(
        project_id=payload.project_id,
        address=payload.address,
        cluster_number=payload.cluster_number,
    )
    db.add(cluster)
    await db.flush()

    # Generate visits (append-only)
    warnings: list[str] = []
    if payload.function_ids or payload.species_ids:
        _, warnings = await generate_visits_for_cluster(
            db=db,
            cluster=cluster,
            function_ids=payload.function_ids,
            species_ids=payload.species_ids,
        )
    await db.commit()
    await db.refresh(cluster)

    # Re-query visits for response
    visits_stmt: Select[tuple[Visit]] = (
        select(Visit)
        .where(Visit.cluster_id == cluster.id)
        .options(selectinload(Visit.functions), selectinload(Visit.species))
    )
    visits = (await db.execute(visits_stmt)).scalars().all()
    return ClusterWithVisitsRead(
        id=cluster.id,
        project_id=cluster.project_id,
        address=cluster.address,
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
                species=[
                    SpeciesCompactRead(
                        id=s.id, name=s.name, abbreviation=s.abbreviation
                    )
                    for s in v.species
                ],
                part_of_day=v.part_of_day,
                start_time=v.start_time,
                start_time_text=(
                    v.start_time_text
                    or derive_start_time_text_for_visit(v.part_of_day, v.start_time)
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
                hup=v.hup,
                dvp=v.dvp,
                remarks_planning=v.remarks_planning,
                remarks_field=v.remarks_field,
            )
            for v in visits
        ],
        warnings=warnings,
    )


@router.post("/{cluster_id}/duplicate", response_model=ClusterRead)
async def duplicate_cluster(
    _: AdminDep, db: DbDep, cluster_id: int, payload: ClusterDuplicate
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
    )
    await db.commit()
    await db.refresh(new_cluster)
    return ClusterRead(
        id=new_cluster.id,
        project_id=new_cluster.project_id,
        address=new_cluster.address,
        cluster_number=new_cluster.cluster_number,
    )


@router.delete(
    "/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_cluster(_: AdminDep, db: DbDep, cluster_id: int) -> Response:
    """Delete a cluster by id; rely on cascade for visits."""

    cluster = await db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # Manually delete associations and visits referencing this cluster
    visit_ids_subq = select(Visit.id).where(Visit.cluster_id == cluster.id)
    # Association tables first to satisfy FKs
    await db.execute(
        delete(visit_researchers).where(
            visit_researchers.c.visit_id.in_(visit_ids_subq)
        )
    )
    await db.execute(
        delete(visit_functions).where(visit_functions.c.visit_id.in_(visit_ids_subq))
    )
    await db.execute(
        delete(visit_species).where(visit_species.c.visit_id.in_(visit_ids_subq))
    )
    # Now delete the visits themselves
    await db.execute(delete(Visit).where(Visit.cluster_id == cluster.id))
    await db.delete(cluster)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
