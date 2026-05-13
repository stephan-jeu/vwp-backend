from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.models.visit import Visit
from app.models.user import User
from app.models.cluster import Cluster
from app.models.project import Project
from app.models.function import Function
from app.services.planning_notification_service import (
    send_planning_emails_for_week,
    _generate_no_visits_email_body,
)


# Mock settings to ensure SMTP check behaves as expected
@pytest.fixture
def mock_smtp_settings(mocker):
    # Retrieve the actual settings object to patch it
    with patch("app.services.planning_notification_service.get_settings") as mock_get:
        mock_settings = MagicMock()
        mock_settings.smtp_host = "localhost"
        mock_settings.admin_email = "admin@example.com"
        mock_get.return_value = mock_settings
        yield mock_settings


@pytest.mark.asyncio
async def test_send_planning_emails(mocker):
    # Mock DB Session
    mock_session = mocker.AsyncMock(name="db_session")

    # Setup Data manually
    # We need to construct objects that have the relationships expected by the service
    # The service accesses: visit.researchers, visit.functions, visit.species, visit.cluster.project

    # Researcher 1
    r1 = User(id=1, full_name="Researcher One", email="r1@example.com")
    # Researcher 2
    r2 = User(id=2, full_name="Researcher Two", email="r2@example.com")

    # Project & Cluster
    proj = Project(id=10, code="P-TEST", location="Loc A")
    cluster = Cluster(id=100, cluster_number="100", address="Street 1", project=proj)

    # Function & Species
    func = Function(id=5, name="Vleermuis")

    # Visit 1: Week 10, R1 & R2
    v1 = Visit(
        id=1001,
        cluster=cluster,
        planned_week=10,
        planned_date=date(2025, 3, 5),
        visit_nr=1,
        part_of_day="Avond",
    )
    # Manually setting relationships (usually SA does this, but for mocks we just assign lists)
    v1.researchers = [r1, r2]
    v1.functions = [func]
    v1.species = []

    # Visit 2: Week 10, R1 only
    v2 = Visit(
        id=1002,
        cluster=cluster,
        planned_week=10,
        planned_date=date(2025, 3, 6),
        visit_nr=2,
        part_of_day="Ochtend",
    )
    v2.researchers = [r1]
    v2.functions = [func]
    v2.species = []

    # Mock execute result
    # (await db.execute(stmt)).scalars().unique().all()
    mock_result = MagicMock()
    mock_result.scalars.return_value.unique.return_value.all.return_value = [v1, v2]
    mock_session.execute.return_value = mock_result

    # Mock settings
    with patch(
        "app.services.planning_notification_service.get_settings"
    ) as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.smtp_host = "localhost"
        mock_settings.admin_email = "admin@example.com"
        mock_get_settings.return_value = mock_settings

        # Mock internal send function
        with patch(
            "app.services.planning_notification_service._send_html_email"
        ) as mock_send:
            # Run Service
            stats = await send_planning_emails_for_week(mock_session, 10, 2025)

            # Verify Stats
            assert stats["total"] == 2  # 2 researchers involved
            assert stats["sent"] == 2

            # Verify send calls
            assert mock_send.call_count == 2

            # Check R1
            # Call args: (to, subject, body)
            # Find call for r1
            calls = mock_send.call_args_list
            r1_call = next((c for c in calls if c[0][0] == "r1@example.com"), None)
            assert r1_call
            assert "Planning Week 10" in r1_call[0][1]
            body_r1 = r1_call[0][2]
            assert "P-TEST" in body_r1
            assert "Researcher Two" in body_r1  # Check teammate

            assert mock_session.execute.called


@pytest.mark.asyncio
async def test_notify_all_researchers_sends_to_unassigned(mocker):
    """When notify_all_researchers=True, researchers without visits also get an email."""
    mock_session = mocker.AsyncMock(name="db_session")

    r1 = User(id=1, full_name="Researcher One", email="r1@example.com")
    r2 = User(id=2, full_name="Researcher Two", email="r2@example.com")

    proj = Project(id=10, code="P-TEST", location="Loc A")
    cluster = Cluster(id=100, cluster_number="100", address="Street 1", project=proj)
    func = Function(id=5, name="Vleermuis")

    v1 = Visit(
        id=1001,
        cluster=cluster,
        planned_week=20,
        planned_date=None,
        visit_nr=1,
        part_of_day="Avond",
    )
    v1.researchers = [r1]
    v1.functions = [func]
    v1.species = []

    # First execute call returns visits (r1 has a visit), second returns all researchers
    visits_result = mocker.MagicMock()
    visits_result.scalars.return_value.unique.return_value.all.return_value = [v1]

    all_researchers_result = mocker.MagicMock()
    all_researchers_result.scalars.return_value.all.return_value = [r1, r2]

    mock_session.execute.side_effect = [visits_result, all_researchers_result]

    with patch(
        "app.services.planning_notification_service.get_settings"
    ) as mock_get_settings:
        mock_settings = mocker.MagicMock()
        mock_settings.smtp_host = "localhost"
        mock_settings.admin_email = "admin@example.com"
        mock_settings.notify_all_researchers = True
        mock_settings.feature_daily_planning = False
        mock_get_settings.return_value = mock_settings

        with patch(
            "app.services.planning_notification_service._send_html_email"
        ) as mock_send:
            stats = await send_planning_emails_for_week(mock_session, 20, 2026)

            assert stats["total"] == 2
            assert stats["sent"] == 2

            calls = mock_send.call_args_list
            r2_call = next((c for c in calls if c[0][0] == "r2@example.com"), None)
            assert r2_call is not None
            body_r2 = r2_call[0][2]
            assert "niet ingepland" in body_r2
            assert "week 20" in body_r2


def test_generate_no_visits_email_body():
    user = User(id=3, full_name="Testpersoon", email="test@example.com")
    body = _generate_no_visits_email_body(user, 20, 2026)
    assert "week 20" in body
    assert "niet ingepland" in body
    assert "11-15 mei" in body
    assert "Testpersoon" in body
