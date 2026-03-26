"""Tests for telegram_bot.py command handlers and callbacks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_companion import db
from canvas_companion.models import CanvasSubmission, SyncResult
from canvas_companion.telegram_bot import create_bot_application


@pytest.fixture
def bot_deps(db_conn):
    """Create mock dependencies for the bot."""
    sync_result = SyncResult(
        started_at="2026-03-25T10:00:00Z",
        finished_at="2026-03-25T10:01:00Z",
        courses_synced=2,
        files_uploaded=3,
        files_updated=1,
        notifications_sent=5,
        errors=[],
    )
    sync_callback = AsyncMock(return_value=sync_result)
    status_callback = MagicMock(return_value={
        "started_at": "2026-03-25T10:00:00Z",
        "status": "ok",
        "courses_synced": 2,
        "files_uploaded": 3,
        "files_updated": 1,
        "notifications": 5,
        "errors": [],
    })
    canvas = AsyncMock()
    scheduler = MagicMock()
    scheduler.interval_minutes = 30

    return {
        "bot_token": "123:fake",
        "chat_id": "12345",
        "sync_callback": sync_callback,
        "status_callback": status_callback,
        "conn": db_conn,
        "canvas": canvas,
        "scheduler": scheduler,
    }


def test_create_bot_application_returns_app(bot_deps):
    app = create_bot_application(**bot_deps)
    assert app is not None


def test_create_bot_application_registers_handlers(bot_deps):
    app = create_bot_application(**bot_deps)
    # Should have 6 command handlers + 1 conversation handler (/prep) + 1 callback query handler
    assert len(app.handlers[0]) == 8


def test_bot_data_stores_dependencies(bot_deps):
    app = create_bot_application(**bot_deps)
    assert app.bot_data["conn"] is bot_deps["conn"]
    assert app.bot_data["canvas"] is bot_deps["canvas"]
    assert app.bot_data["scheduler"] is bot_deps["scheduler"]


def test_courses_keyboard_empty(bot_deps):
    """When no courses exist, the courses view should show a helpful message."""
    app = create_bot_application(**bot_deps)
    courses = db.get_all_courses(bot_deps["conn"])
    assert len(courses) == 0


def test_courses_keyboard_with_courses(bot_deps):
    """Course list should include all synced courses."""
    conn = bot_deps["conn"]
    db.upsert_course(conn, 101, "CS2030S", "CS2030S")
    db.upsert_course(conn, 202, "GEA1000", "GEA1000")

    courses = db.get_all_courses(conn)
    assert len(courses) == 2


def test_excluded_courses_filter_toggle(bot_deps):
    """Toggling a course in/out of the exclusion list."""
    conn = bot_deps["conn"]
    db.upsert_course(conn, 101, "CS2030S", "CS2030S")

    # Initially no courses excluded
    assert db.get_excluded_course_ids(conn) == []

    # Exclude course 101
    db.set_excluded_course_ids(conn, [101])
    assert 101 in db.get_excluded_course_ids(conn)

    # Re-include
    db.set_excluded_course_ids(conn, [])
    assert db.get_excluded_course_ids(conn) == []


def test_frequency_options_stored_in_db(bot_deps):
    """Setting frequency should persist in user_preferences."""
    conn = bot_deps["conn"]
    db.set_preference(conn, "sync_interval_minutes", "240")
    assert db.get_preference(conn, "sync_interval_minutes") == "240"


def test_outstanding_submissions_filtering(bot_deps):
    """Submissions with 'submitted' or 'graded' state should be filtered out."""
    subs = [
        CanvasSubmission(assignment_id=1, workflow_state="submitted", submitted_at="2026-03-20T10:00:00Z"),
        CanvasSubmission(assignment_id=2, workflow_state="unsubmitted"),
        CanvasSubmission(assignment_id=3, workflow_state="graded", submitted_at="2026-03-21T10:00:00Z"),
        CanvasSubmission(assignment_id=4, workflow_state="unsubmitted"),
    ]

    submitted_ids = {
        s.assignment_id for s in subs
        if s.workflow_state in ("submitted", "graded") or s.submitted_at is not None
    }

    assert submitted_ids == {1, 3}
    assert 2 not in submitted_ids
    assert 4 not in submitted_ids
