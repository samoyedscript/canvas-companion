"""Tests for user preferences in db.py."""

from __future__ import annotations

from canvas_companion import db


def test_user_preferences_table_created(db_conn):
    cursor = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'"
    )
    assert cursor.fetchone() is not None


def test_get_preference_missing_returns_none(db_conn):
    assert db.get_preference(db_conn, "nonexistent") is None


def test_set_and_get_preference(db_conn):
    db.set_preference(db_conn, "theme", "dark")
    assert db.get_preference(db_conn, "theme") == "dark"


def test_set_preference_upserts(db_conn):
    db.set_preference(db_conn, "color", "red")
    db.set_preference(db_conn, "color", "blue")
    assert db.get_preference(db_conn, "color") == "blue"


def test_excluded_course_ids_default_empty(db_conn):
    assert db.get_excluded_course_ids(db_conn) == []


def test_set_and_get_excluded_course_ids(db_conn):
    db.set_excluded_course_ids(db_conn, [101, 202, 303])
    assert db.get_excluded_course_ids(db_conn) == [101, 202, 303]


def test_set_excluded_course_ids_overwrites(db_conn):
    db.set_excluded_course_ids(db_conn, [101, 202])
    db.set_excluded_course_ids(db_conn, [303])
    assert db.get_excluded_course_ids(db_conn) == [303]


def test_set_excluded_course_ids_empty(db_conn):
    db.set_excluded_course_ids(db_conn, [101])
    db.set_excluded_course_ids(db_conn, [])
    assert db.get_excluded_course_ids(db_conn) == []


def test_get_assignments_for_course_empty(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    assert db.get_assignments_for_course(db_conn, 101) == []


def test_get_assignments_for_course_ordered_by_due(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.upsert_tracked_assignment(db_conn, 1001, 101, "HW2", "2026-04-15T23:59:00Z")
    db.upsert_tracked_assignment(db_conn, 1002, 101, "HW1", "2026-04-01T23:59:00Z")
    db.upsert_tracked_assignment(db_conn, 1003, 101, "HW3", None)  # no due date

    assignments = db.get_assignments_for_course(db_conn, 101)
    assert len(assignments) == 3
    # NULL due_at sorts first in SQLite ORDER BY
    assert assignments[0]["name"] == "HW3"
    assert assignments[1]["name"] == "HW1"
    assert assignments[2]["name"] == "HW2"


def test_get_assignments_for_course_filters_by_course(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.upsert_course(db_conn, 202, "CS202", "CS202")
    db.upsert_tracked_assignment(db_conn, 1001, 101, "HW1", "2026-04-01T23:59:00Z")
    db.upsert_tracked_assignment(db_conn, 2001, 202, "HW1", "2026-04-01T23:59:00Z")

    assert len(db.get_assignments_for_course(db_conn, 101)) == 1
    assert len(db.get_assignments_for_course(db_conn, 202)) == 1
