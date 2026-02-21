from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
import smtplib
from email.message import EmailMessage

from sqlalchemy import select, and_
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.engine import Row

from core.settings import get_settings
from app.models.visit import Visit
from app.models.cluster import Cluster
from app.models.user import User
from app.models.function import Function
from app.models.species import Species
from app.services.email_service import send_email

logger = logging.getLogger(__name__)


def _work_week_bounds(current_year: int, iso_week: int) -> tuple[date, date]:
    first_day = date.fromisocalendar(current_year, iso_week, 1)
    # The week is Mon-Sun, but planning is typically Mon-Fri. 
    # Let's cover the whole week just in case.
    last_day = first_day + timedelta(days=6)
    return first_day, last_day


async def send_planning_emails_for_week(db: Session, week: int, year: int) -> dict:
    """
    Sends an email to each researcher who has visits planned in the specified week.
    Returns a summary dict: {'total': int, 'sent': int, 'failed': int, 'skipped': int}.
    """
    
    # 1. Fetch relevant visits
    # Similar query logic as in planning.py::get_planning but we need to ensure we get all visits for the week
    week_start, week_end = _work_week_bounds(year, week)
    
    # We want visits active (not soft deleted), assigned to researchers, for this week.
    stmt = (
        select(Visit)
        .where(Visit.deleted_at.is_(None))  # Active visits
        .options(
            selectinload(Visit.researchers),
            selectinload(Visit.functions),
            selectinload(Visit.species),
            selectinload(Visit.cluster).selectinload(Cluster.project),
        )
        .where(
             # Has at least one researcher
            Visit.researchers.any()
        )
        .where(
            # Planned for this week
            (Visit.planned_week == week)
            | and_(
                Visit.from_date <= week_end,
                Visit.to_date >= week_start,
            )
        )
    )
    
    visits: list[Visit] = (await db.execute(stmt)).scalars().unique().all()
    
    if not visits:
        return {"total": 0, "sent": 0, "failed": 0, "skipped": 0}

    # 2. Group by researcher
    visits_by_researcher: dict[int, list[Visit]] = defaultdict(list)
    researchers_map: dict[int, User] = {}

    for visit in visits:
        for researcher in visit.researchers:
            if not researcher.email:
                continue # Skip researchers without email
            
            visits_by_researcher[researcher.id].append(visit)
            researchers_map[researcher.id] = researcher

    # 3. Generate and send emails
    stats = {"total": len(visits_by_researcher), "sent": 0, "failed": 0, "skipped": 0}

    settings = get_settings()
    frontend_url = "http://localhost:3000" # TODO: Should ideally come from settings too for prod
    
    for researcher_id, researcher_visits in visits_by_researcher.items():
        researcher = researchers_map[researcher_id]
        
        try:
            # Sort visits by date/time
            researcher_visits.sort(key=lambda v: (v.planned_date or date.max, v.start_time_text or ""))
            
            subject = f"Planning Week {week} - Veldwerkplanning"
            html_body = _generate_email_body(researcher, researcher_visits, week, frontend_url)
            
            # Use the HTML sending capability (we need to update send_email to support HTML or just send as plain text/html hybrid)
            # The current send_email in email_service.py uses `msg.set_content(body)` which implies text/plain.
            # We should probably extend email_service or use a local helper here that does HTML.
            # For now, let's create a local helper to send HTML email.
            _send_html_email(researcher.email, subject, html_body)
            
            stats["sent"] += 1
            
        except Exception as e:
            logger.exception(f"Failed to send planning email to {researcher.email}: {e}")
            stats["failed"] += 1

    return stats


def _generate_email_body(user: User, visits: list[Visit], week: int, frontend_url: str) -> str:
    # Basic HTML template
    rows = ""
    for v in visits:
        project_code = v.cluster.project.code if v.cluster and v.cluster.project else "?"
        cluster_info = f"C{v.cluster.cluster_number}" if v.cluster else "?"
        location = v.cluster.project.location if v.cluster and v.cluster.project else "?"
        address = v.cluster.address if v.cluster else ""
        
        # Day and Date
        day_str = "?"
        if v.planned_date:
            days = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
            day_str = f"{days[v.planned_date.weekday()]} {v.planned_date.strftime('%d-%m')}"
        
        # Functions & Species
        funcs = ", ".join([f.name for f in v.functions])
        specs = ", ".join([s.name for s in v.species])
        content_desc = f"{funcs}"
        if specs:
            content_desc += f" / {specs}"

        # Team
        team = [r.full_name for r in v.researchers if r.id != user.id]
        team_str = ", ".join(team) if team else "-"
        
        # Link
        link = f"{frontend_url}/visits/{v.id}"
        
        rows += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 10px; vertical-align: top;">
                <strong>{day_str}</strong><br>
                <span style="font-size: 0.9em; color: #666;">{v.part_of_day or '-'}</span>
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
            <td style="padding: 10px; vertical-align: top; text-align: right;">
                <a href="{link}" style="background-color: #0ea5e9; color: white; padding: 5px 10px; text-decoration: none; border-radius: 4px; font-size: 0.9em;">Details</a>
            </td>
        </tr>
        """

    return f"""
    <html>
    <body style="font-family: sans-serif; color: #333;">
        <h2>Planning Week {week}</h2>
        <p>Beste {user.full_name or 'collega'},</p>
        <p>Hieronder vind je jouw geplande bezoeken voor week {week}.</p>
        
        <table style="width: 100%; border-collapse: collapse; text-align: left; margin-top: 20px;">
            <thead>
                <tr style="background-color: #f8fafc; border-bottom: 2px solid #e2e8f0;">
                    <th style="padding: 10px;">Datum & Dagdeel</th>
                    <th style="padding: 10px;">Locatie</th>
                    <th style="padding: 10px;">Activiteit</th>
                    <th style="padding: 10px;">Team</th>
                    <th style="padding: 10px;"></th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        
        <p style="margin-top: 30px; font-size: 0.9em; color: #666;">
            Let op: deze planning is onder voorbehoud. Kijk altijd in de app voor de meest actuele informatie.
        </p>
    </body>
    </html>
    """

def _send_html_email(to: str, subject: str, html_body: str) -> None:
    settings = get_settings()
    
    # Check if we are in a production-like environment regarding SMTP
    # If using the base email_service logic, it might just print if no host.
    # We duplicate the logic slightly here to ensure HTML support.
    
    if not settings.smtp_host:
        print(f"SMTP not configured. Mock HTML email to {to}: {subject}")
        # print(html_body) # Optional: print body for debug
        return

    msg = EmailMessage()
    msg.set_content("Bekijk deze e-mail in een e-mailclient die HTML ondersteunt.") # Fallback
    msg.add_alternative(html_body, subtype='html')
    
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
