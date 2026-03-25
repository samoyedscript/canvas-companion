"""Integration tests for sync_engine.py with mocked external services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from canvas_companion import db
from canvas_companion.models import (
    CanvasAnnouncement,
    CanvasAssignment,
    CanvasCourse,
    CanvasFile,
)
from canvas_companion.sync_engine import run_sync


def _make_canvas_mock(courses, assignments_by_course, announcements, files_by_course):
    """Create a mocked CanvasClient."""
    canvas = AsyncMock()
    canvas.get_active_courses.return_value = courses

    async def get_assignments(course_id):
        return assignments_by_course.get(course_id, [])

    async def get_announcements(course_ids, start_date=None):
        return [a for a in announcements if a.course_id in course_ids]

    async def get_files(course_id):
        return files_by_course.get(course_id, [])

    async def download_file(url):
        return b"file content"

    canvas.get_assignments = AsyncMock(side_effect=get_assignments)
    canvas.get_announcements = AsyncMock(side_effect=get_announcements)
    canvas.get_files = AsyncMock(side_effect=get_files)
    canvas.download_file = AsyncMock(side_effect=download_file)
    return canvas


def _make_drive_mock():
    """Create a mocked DriveSync."""
    drive = MagicMock()
    drive.ensure_root_folder.return_value = "root_folder_id"
    drive.ensure_course_folder.return_value = "course_folder_id"

    upload_counter = 0

    def upload_file(name, content, mime_type, parent_id):
        nonlocal upload_counter
        upload_counter += 1
        return f"drive_file_{upload_counter}", f"https://drive.google.com/file/{upload_counter}"

    def update_file(drive_id, name, content, mime_type):
        return drive_id, f"https://drive.google.com/file/{drive_id}_updated"

    drive.upload_file = MagicMock(side_effect=upload_file)
    drive.update_file = MagicMock(side_effect=update_file)
    return drive


def _make_notifier_mock():
    """Create a mocked TelegramNotifier."""
    notifier = AsyncMock()
    return notifier


@pytest.fixture
def sample_courses():
    return [
        CanvasCourse(id=101, name="CS101", course_code="CS101"),
        CanvasCourse(id=202, name="CS202", course_code="CS202"),
    ]


@pytest.fixture
def sample_assignments():
    future = datetime.now(timezone.utc) + timedelta(days=10)
    return {
        101: [
            CanvasAssignment(
                id=1001, course_id=101, name="HW1",
                due_at=future,
                html_url="https://canvas.test/a/1001",
            ),
        ],
        202: [
            CanvasAssignment(
                id=2001, course_id=202, name="Project",
                due_at=future,
                html_url="https://canvas.test/a/2001",
            ),
        ],
    }


@pytest.fixture
def sample_announcements():
    return [
        CanvasAnnouncement(
            id=5001, course_id=101, title="Welcome",
            message="Hello!", posted_at=datetime.now(timezone.utc),
        ),
    ]


@pytest.fixture
def sample_files():
    return {
        101: [
            CanvasFile(
                id=9001, course_id=101, display_name="lecture.pdf",
                url="https://canvas.test/files/9001",
                updated_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
                size=1024, content_type="application/pdf",
            ),
        ],
        202: [],
    }


@pytest.mark.asyncio
async def test_first_sync_creates_everything(
    db_conn, sample_courses, sample_assignments, sample_announcements, sample_files,
):
    canvas = _make_canvas_mock(
        sample_courses, sample_assignments, sample_announcements, sample_files,
    )
    drive = _make_drive_mock()
    notifier = _make_notifier_mock()

    result = await run_sync(canvas, drive, notifier, db_conn)

    assert result.courses_synced == 2
    assert result.files_uploaded == 1
    assert result.files_updated == 0
    assert result.notifications_sent > 0
    assert result.errors == []

    # Verify DB state
    assert db.get_course(db_conn, 101) is not None
    assert db.get_course(db_conn, 202) is not None
    assert db.get_tracked_file(db_conn, 9001) is not None
    assert db.get_tracked_assignment(db_conn, 1001) is not None
    assert db.get_tracked_announcement(db_conn, 5001) is not None


@pytest.mark.asyncio
async def test_second_sync_no_changes_no_notifications(
    db_conn, sample_courses, sample_assignments, sample_announcements, sample_files,
):
    canvas = _make_canvas_mock(
        sample_courses, sample_assignments, sample_announcements, sample_files,
    )
    drive = _make_drive_mock()
    notifier = _make_notifier_mock()

    # First sync
    await run_sync(canvas, drive, notifier, db_conn)
    notifier.reset_mock()

    # Second sync — same data
    result = await run_sync(canvas, drive, notifier, db_conn)
    assert result.files_uploaded == 0
    assert result.files_updated == 0
    # No new notifications should be sent
    notifier.notify_new_assignment.assert_not_called()
    notifier.notify_new_announcement.assert_not_called()
    notifier.notify_file_synced.assert_not_called()


@pytest.mark.asyncio
async def test_due_date_change_triggers_notification(
    db_conn, sample_courses, sample_announcements, sample_files,
):
    future1 = datetime.now(timezone.utc) + timedelta(days=10)
    future2 = datetime.now(timezone.utc) + timedelta(days=5)

    assignments_v1 = {
        101: [
            CanvasAssignment(
                id=1001, course_id=101, name="HW1",
                due_at=future1,
                html_url="https://canvas.test/a/1001",
            ),
        ],
        202: [],
    }

    canvas = _make_canvas_mock(
        sample_courses, assignments_v1, sample_announcements, sample_files,
    )
    drive = _make_drive_mock()
    notifier = _make_notifier_mock()

    # First sync
    await run_sync(canvas, drive, notifier, db_conn)
    notifier.reset_mock()

    # Second sync — due date changed
    assignments_v2 = {
        101: [
            CanvasAssignment(
                id=1001, course_id=101, name="HW1",
                due_at=future2,
                html_url="https://canvas.test/a/1001",
            ),
        ],
        202: [],
    }
    canvas2 = _make_canvas_mock(
        sample_courses, assignments_v2, sample_announcements, sample_files,
    )
    result = await run_sync(canvas2, drive, notifier, db_conn)

    notifier.notify_due_date_changed.assert_called_once()


@pytest.mark.asyncio
async def test_file_update_triggers_notification(
    db_conn, sample_courses, sample_assignments, sample_announcements,
):
    files_v1 = {
        101: [
            CanvasFile(
                id=9001, course_id=101, display_name="lecture.pdf",
                url="https://canvas.test/files/9001",
                updated_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
                size=1024, content_type="application/pdf",
            ),
        ],
        202: [],
    }

    canvas = _make_canvas_mock(
        sample_courses, sample_assignments, sample_announcements, files_v1,
    )
    drive = _make_drive_mock()
    notifier = _make_notifier_mock()

    await run_sync(canvas, drive, notifier, db_conn)
    notifier.reset_mock()
    drive.upload_file.reset_mock()

    # File updated on Canvas
    files_v2 = {
        101: [
            CanvasFile(
                id=9001, course_id=101, display_name="lecture.pdf",
                url="https://canvas.test/files/9001",
                updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
                size=2048, content_type="application/pdf",
            ),
        ],
        202: [],
    }
    canvas2 = _make_canvas_mock(
        sample_courses, sample_assignments, sample_announcements, files_v2,
    )
    result = await run_sync(canvas2, drive, notifier, db_conn)

    assert result.files_updated == 1
    drive.update_file.assert_called_once()
    notifier.notify_file_synced.assert_called_once()
    # Verify is_update=True was passed
    call_kwargs = notifier.notify_file_synced.call_args
    assert call_kwargs[1].get("is_update") is True or call_kwargs[0][3] is True


@pytest.mark.asyncio
async def test_course_error_isolated(db_conn, sample_announcements):
    """An error in one course should not stop others."""
    courses = [
        CanvasCourse(id=101, name="CS101", course_code="CS101"),
        CanvasCourse(id=202, name="CS202", course_code="CS202"),
    ]

    canvas = AsyncMock()
    canvas.get_active_courses.return_value = courses

    # Assignments for course 101 will raise
    async def get_assignments(course_id):
        if course_id == 101:
            raise RuntimeError("Canvas API error")
        return []

    canvas.get_assignments = AsyncMock(side_effect=get_assignments)
    canvas.get_announcements = AsyncMock(return_value=[])
    canvas.get_files = AsyncMock(return_value=[])

    drive = _make_drive_mock()
    notifier = _make_notifier_mock()

    result = await run_sync(canvas, drive, notifier, db_conn)

    assert result.courses_synced == 2
    assert len(result.errors) == 1
    assert "CS101" in result.errors[0]
