"""Tests for db.py."""

from __future__ import annotations

from canvas_companion import db


def test_init_schema_creates_tables(db_conn):
    """Tables should exist after init_schema."""
    cursor = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row["name"] for row in cursor.fetchall()}
    expected = {
        "courses",
        "tracked_files",
        "tracked_assignments",
        "tracked_announcements",
        "notification_history",
        "sync_runs",
        "file_chunks",
        "prep_sessions",
    }
    assert expected.issubset(tables)


def test_upsert_and_get_course(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    course = db.get_course(db_conn, 101)
    assert course is not None
    assert course["name"] == "CS101"
    assert course["drive_folder_id"] is None

    # Update name
    db.upsert_course(db_conn, 101, "CS101 Updated", "CS101")
    course = db.get_course(db_conn, 101)
    assert course["name"] == "CS101 Updated"


def test_set_drive_folder_id(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.set_drive_folder_id(db_conn, 101, "folder_abc")
    course = db.get_course(db_conn, 101)
    assert course["drive_folder_id"] == "folder_abc"


def test_upsert_and_get_tracked_file(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.upsert_tracked_file(
        db_conn, 9001, 101, "lecture01.pdf",
        "2026-03-18T08:00:00Z", "drive_id_1", "https://drive.google.com/file/1",
    )
    tracked = db.get_tracked_file(db_conn, 9001)
    assert tracked is not None
    assert tracked["display_name"] == "lecture01.pdf"
    assert tracked["drive_file_id"] == "drive_id_1"

    # Update
    db.upsert_tracked_file(
        db_conn, 9001, 101, "lecture01.pdf",
        "2026-03-19T08:00:00Z", "drive_id_1_v2", "https://drive.google.com/file/1v2",
    )
    tracked = db.get_tracked_file(db_conn, 9001)
    assert tracked["canvas_updated_at"] == "2026-03-19T08:00:00Z"
    assert tracked["drive_file_id"] == "drive_id_1_v2"


def test_get_tracked_file_not_found(db_conn):
    assert db.get_tracked_file(db_conn, 9999) is None


def test_upsert_and_get_tracked_assignment(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.upsert_tracked_assignment(db_conn, 1001, 101, "HW1", "2026-04-01T23:59:00Z", "normal")
    tracked = db.get_tracked_assignment(db_conn, 1001)
    assert tracked is not None
    assert tracked["name"] == "HW1"
    assert tracked["due_at"] == "2026-04-01T23:59:00Z"
    assert tracked["last_notified_urgency"] == "normal"


def test_announcement_dedup(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    assert db.get_tracked_announcement(db_conn, 5001) is None

    db.mark_announcement_notified(db_conn, 5001, 101, "Welcome")
    assert db.get_tracked_announcement(db_conn, 5001) is not None

    # Inserting again should not raise (INSERT OR IGNORE)
    db.mark_announcement_notified(db_conn, 5001, 101, "Welcome")


def test_notification_dedup(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    assert not db.was_notification_sent(db_conn, "new_assignment", 1001, "hash_abc")

    db.record_notification(db_conn, "new_assignment", 1001, 101, "hash_abc")
    assert db.was_notification_sent(db_conn, "new_assignment", 1001, "hash_abc")
    assert not db.was_notification_sent(db_conn, "new_assignment", 1001, "hash_different")


def test_sync_run_recording(db_conn):
    assert db.get_last_sync_run(db_conn) is None

    db.record_sync_run(
        db_conn, "2026-03-23T10:00:00Z", "2026-03-23T10:01:00Z",
        2, 3, 1, 5, [],
    )
    last = db.get_last_sync_run(db_conn)
    assert last is not None
    assert last["courses_synced"] == 2
    assert last["files_uploaded"] == 3
    assert last["status"] == "ok"
    assert last["errors"] == []

    # Record another with errors
    db.record_sync_run(
        db_conn, "2026-03-23T11:00:00Z", "2026-03-23T11:01:00Z",
        1, 0, 0, 0, ["Something failed"],
    )
    last = db.get_last_sync_run(db_conn)
    assert last["status"] == "error"
    assert last["errors"] == ["Something failed"]


def test_get_all_courses(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.upsert_course(db_conn, 202, "CS202", "CS202")
    courses = db.get_all_courses(db_conn)
    assert len(courses) == 2
