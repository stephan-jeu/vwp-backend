from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from email.message import EmailMessage

from sqlalchemy import select, and_, or_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.settings import get_settings
from app.models.visit import Visit
from app.models.cluster import Cluster
from app.models.user import User

logger = logging.getLogger(__name__)


def _work_week_bounds(current_year: int, iso_week: int) -> tuple[date, date]:
    first_day = date.fromisocalendar(current_year, iso_week, 1)
    # The week is Mon-Sun, but planning is typically Mon-Fri.
    # Let's cover the whole week just in case.
    last_day = first_day + timedelta(days=6)
    return first_day, last_day


async def send_planning_emails_for_week(db: AsyncSession, week: int, year: int) -> dict:
    """
    Sends an email to each researcher who has visits planned in the specified week.
    When NOTIFY_ALL_RESEARCHERS=true, also sends to researchers without any visits.
    Returns a summary dict: {'total': int, 'sent': int, 'failed': int, 'skipped': int}.
    """

    # 1. Fetch relevant visits
    week_start, week_end = _work_week_bounds(year, week)

    stmt = (
        select(Visit)
        .where(Visit.deleted_at.is_(None))
        .options(
            selectinload(Visit.researchers),
            selectinload(Visit.functions),
            selectinload(Visit.species),
            selectinload(Visit.cluster).selectinload(Cluster.project),
        )
        .where(Visit.researchers.any())
        .where(
            and_(
                Visit.planned_week == week,
                or_(
                    Visit.from_date.is_(None),
                    extract("year", Visit.from_date) == year,
                ),
            )
            | and_(
                Visit.planned_date >= week_start,
                Visit.planned_date <= week_end,
            )
        )
    )

    visits: list[Visit] = list((await db.execute(stmt)).scalars().unique().all())

    # 2. Group by researcher
    visits_by_researcher: dict[int, list[Visit]] = defaultdict(list)
    researchers_map: dict[int, User] = {}

    for visit in visits:
        for researcher in visit.researchers:
            if researcher.deleted_at is not None:
                continue
            if not researcher.email:
                continue

            visits_by_researcher[researcher.id].append(visit)
            researchers_map[researcher.id] = researcher

    # 3. When NOTIFY_ALL_RESEARCHERS is enabled, add all active researchers
    settings = get_settings()
    if settings.notify_all_researchers:
        all_researchers_stmt = select(User).where(
            User.deleted_at.is_(None),
            User.email.isnot(None),
            User.email != "",
        )
        all_researchers: list[User] = list(
            (await db.execute(all_researchers_stmt)).scalars().all()
        )
        for researcher in all_researchers:
            if researcher.id not in researchers_map:
                researchers_map[researcher.id] = researcher
                # Empty list signals "no visits" for this researcher

    # 4. Generate and send emails
    stats = {"total": len(researchers_map), "sent": 0, "failed": 0, "skipped": 0}

    frontend_url = settings.frontend_url

    for researcher_id, researcher in researchers_map.items():
        researcher_visits = visits_by_researcher.get(researcher_id, [])

        try:
            researcher_visits.sort(
                key=lambda v: (v.planned_date or date.max, v.start_time_text or "")
            )

            subject = f"Planning Week {week} - Veldwerkplanning"
            if researcher_visits:
                html_body = _generate_email_body(
                    researcher, researcher_visits, week, frontend_url
                )
            else:
                html_body = _generate_no_visits_email_body(
                    researcher, week, year, frontend_url
                )

            ics_attachment: bytes | None = None
            if settings.enable_ical and researcher_visits:
                from app.services.ical_service import build_week_ical
                ics_attachment = build_week_ical(researcher_visits, week, year)

            _send_html_email(researcher.email, subject, html_body, ics_attachment, ics_week=week)
            stats["sent"] += 1

        except Exception as e:
            logger.exception(
                f"Failed to send planning email to {researcher.email}: {e}"
            )
            stats["failed"] += 1

    return stats


def _generate_email_body(
    user: User, visits: list[Visit], week: int, frontend_url: str
) -> str:
    # Basic HTML template
    rows = ""
    for v in visits:
        project_code = (
            v.cluster.project.code if v.cluster and v.cluster.project else "?"
        )
        cluster_info = f"C{v.cluster.cluster_number}" if v.cluster else "?"
        location = (
            (v.cluster.location if v.cluster and v.cluster.location else None)
            or (v.cluster.project.location if v.cluster and v.cluster.project else None)
            or "?"
        )
        address = v.cluster.address if v.cluster else ""

        # Day and Date / Week
        day_str = ""
        part_of_day_str = v.part_of_day or "-"

        settings = get_settings()
        if settings.feature_daily_planning:
            if v.planned_date:
                days = [
                    "Maandag",
                    "Dinsdag",
                    "Woensdag",
                    "Donderdag",
                    "Vrijdag",
                    "Zaterdag",
                    "Zondag",
                ]
                day_str = f"{days[v.planned_date.weekday()]} {v.planned_date.strftime('%d-%m')}"
        else:
            # Weekly planning logic
            if v.from_date and v.to_date:
                # Calculate if the visit window is entirely within the planned week
                week_start, week_end = _work_week_bounds(v.from_date.year, week)

                if v.from_date >= week_start and v.to_date <= week_end:
                    days = [
                        "Maandag",
                        "Dinsdag",
                        "Woensdag",
                        "Donderdag",
                        "Vrijdag",
                        "Zaterdag",
                        "Zondag",
                    ]
                    if v.from_date == v.to_date:
                        day_str = f"{days[v.from_date.weekday()]} {v.from_date.strftime('%d-%m')}"
                    else:
                        day_str = f"Vanaf {days[v.from_date.weekday()].lower()} {v.from_date.strftime('%d-%m')} t/m {days[v.to_date.weekday()].lower()} {v.to_date.strftime('%d-%m')}"
                elif v.from_date >= week_start:
                    days = [
                        "Maandag",
                        "Dinsdag",
                        "Woensdag",
                        "Donderdag",
                        "Vrijdag",
                        "Zaterdag",
                        "Zondag",
                    ]
                    day_str = f"Vanaf {days[v.from_date.weekday()].lower()} {v.from_date.strftime('%d-%m')}"
                elif v.to_date <= week_end:
                    days = [
                        "Maandag",
                        "Dinsdag",
                        "Woensdag",
                        "Donderdag",
                        "Vrijdag",
                        "Zaterdag",
                        "Zondag",
                    ]
                    day_str = f"Uiterlijk {days[v.to_date.weekday()].lower()} {v.to_date.strftime('%d-%m')}"
                else:
                    day_str = "Hele week"
            else:
                day_str = "Hele week"

        # Functions & Species
        funcs = ", ".join([f.name for f in v.functions])
        specs = ", ".join([s.name for s in v.species])
        content_desc = f"{funcs}"
        if specs:
            content_desc += f" / {specs}"

        # Team
        team = [r.full_name for r in v.researchers if r.id != user.id and r.full_name]
        team_str = ", ".join(team) if team else "-"

        # Link
        link = f"{frontend_url}/visits/{v.id}"

        rows += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 10px; vertical-align: top;">
                <strong>{day_str}</strong><br>
                <span style="font-size: 0.9em; color: #666;">{part_of_day_str}</span><br>
                <a href="{link}" style="display: inline-block; margin-top: 6px; background-color: #0ea5e9; color: white; padding: 4px 10px; text-decoration: none; border-radius: 4px; font-size: 0.85em; white-space: nowrap;">Details</a>
            </td>
            <td style="padding: 10px; vertical-align: top;">
                <strong>{project_code} {cluster_info}</strong><br>
                {location}<br>
                <span style="font-size: 0.9em; color: #666;">{address}</span>
            </td>
            <td style="padding: 10px; vertical-align: top;">
                {content_desc}
            </td>
            <td style="padding: 10px; vertical-align: top;">
                {team_str}
            </td>
        </tr>
        """

    return f"""
    <html>
    <body style="font-family: sans-serif; color: #333;">
        <h2>Planning Week {week}</h2>
        <p>Beste {user.full_name or "collega"},</p>
        <p>Hieronder vind je jouw geplande bezoeken voor week {week}.</p>
        
        <table style="width: 100%; border-collapse: collapse; text-align: left; margin-top: 20px;">
            <thead>
                <tr style="background-color: #f8fafc; border-bottom: 2px solid #e2e8f0;">
                    <th style="padding: 10px;">Datum & Dagdeel</th>
                    <th style="padding: 10px;">Locatie</th>
                    <th style="padding: 10px;">Activiteit</th>
                    <th style="padding: 10px;">Team</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        
        <p style="margin-top: 30px; font-size: 0.9em; color: #666;">
            Let op: deze planning is onder voorbehoud. Kijk altijd in <a href="{frontend_url}">de app</a> voor de meest actuele informatie.
        </p>
    </body>
    </html>
    """


def _generate_no_visits_email_body(user: User, week: int, year: int, frontend_url: str) -> str:
    monday = date.fromisocalendar(year, week, 1)
    friday = monday + timedelta(days=4)
    nl_months = [
        "januari", "februari", "maart", "april", "mei", "juni",
        "juli", "augustus", "september", "oktober", "november", "december",
    ]
    month_name = nl_months[monday.month - 1]
    date_range = f"{monday.day}-{friday.day} {month_name}"

    return f"""
    <html>
    <body style="font-family: sans-serif; color: #333;">
        <h2>Planning Week {week}</h2>
        <p>Beste {user.full_name or "collega"},</p>
        <p>Je staat niet ingepland voor bezoeken voor week {week} ({date_range}).</p>
        <p style="margin-top: 30px; font-size: 0.9em; color: #666;">
            Kijk altijd in <a href="{frontend_url}">de app</a> voor de meest actuele informatie.
        </p>
    </body>
    </html>
    """


def _send_html_email(to: str, subject: str, html_body: str, ics_attachment: bytes | None = None, ics_week: int | None = None) -> None:
    settings = get_settings()

    # Check if we are in a production-like environment regarding SMTP
    # If using the base email_service logic, it might just print if no host.
    # We duplicate the logic slightly here to ensure HTML support.

    if not settings.smtp_host:
        print(f"SMTP not configured. Mock HTML email to {to}: {subject}")
        # print(html_body) # Optional: print body for debug
        return

    msg = EmailMessage()
    msg.set_content(
        "Bekijk deze e-mail in een e-mailclient die HTML ondersteunt."
    )  # Fallback
    msg.add_alternative(html_body, subtype="html")

    if ics_attachment:
        filename = f"planning-week-{ics_week}.ics" if ics_week is not None else "planning.ics"
        msg.add_attachment(
            ics_attachment,
            maintype="text",
            subtype="calendar",
            filename=filename,
        )

    msg["Subject"] = subject
    msg["From"] = settings.admin_email
    msg["To"] = to

    try:
        from app.services.email_service import start_smtp_session

        with start_smtp_session() as server:
            server.send_message(msg)
    except Exception as e:
        # Re-raise to be caught by caller for stats
        raise e
