import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

from app.schemas.trash import TrashItem, TrashKind
from app.services.trash_service import purge_old_trash

@pytest.mark.asyncio
async def test_purge_old_trash(mocker):
    # Setup Data
    now = datetime.now(timezone.utc)
    
    # Item 1: Deleted 40 days ago (Should be purged)
    item_old = TrashItem(
        id=1,
        kind=TrashKind.PROJECT,
        label="Old Project",
        project_code="P-OLD",
        deleted_at=now - timedelta(days=40)
    )
    
    # Item 2: Deleted 10 days ago (Should be kept)
    item_recent = TrashItem(
        id=2,
        kind=TrashKind.CLUSTER,
        label="Recent Cluster",
        project_code="P-NEW",
        cluster_number="1",
        deleted_at=now - timedelta(days=10)
    )
    
    db_session = mocker.AsyncMock()

    with patch("app.services.trash_service.list_trash_items") as mock_list, \
         patch("app.services.trash_service.hard_delete_trash_item") as mock_hard_delete:
         
        mock_list.return_value = [item_old, item_recent]
        mock_hard_delete.return_value = None

        count = await purge_old_trash(db_session, retention_days=30)

        assert count == 1
        mock_list.assert_called_once_with(db_session)
        mock_hard_delete.assert_called_once_with(db_session, TrashKind.PROJECT, 1)

@pytest.mark.asyncio
async def test_purge_old_trash_handles_exception_and_continues(mocker):
    now = datetime.now(timezone.utc)
    
    item_old_1 = TrashItem(
        id=1,
        kind=TrashKind.PROJECT,
        label="Old Project 1",
        project_code="P-OLD1",
        deleted_at=now - timedelta(days=40)
    )
    item_old_2 = TrashItem(
        id=2,
        kind=TrashKind.PROJECT,
        label="Old Project 2",
        project_code="P-OLD2",
        deleted_at=now - timedelta(days=40)
    )
    
    db_session = mocker.AsyncMock()

    with patch("app.services.trash_service.list_trash_items") as mock_list, \
         patch("app.services.trash_service.hard_delete_trash_item") as mock_hard_delete:
         
        mock_list.return_value = [item_old_1, item_old_2]
        
        # Make the first one fail
        mock_hard_delete.side_effect = [Exception("error"), None]

        count = await purge_old_trash(db_session, retention_days=30)

        # Should continue and delete the second one
        assert count == 1
        assert mock_hard_delete.call_count == 2
