"""SQLite database schema and data access layer."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return a connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS courses (
            course_id       INTEGER PRIMARY KEY,
            name            TEXT NOT NULL,
            course_code     TEXT,
            drive_folder_id TEXT,
            first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tracked_files (
            canvas_file_id    INTEGER PRIMARY KEY,
            course_id         INTEGER NOT NULL REFERENCES courses(course_id),
            display_name      TEXT NOT NULL,
            canvas_updated_at TEXT NOT NULL,
            drive_file_id     TEXT NOT NULL,
            drive_web_link    TEXT NOT NULL,
            synced_at         TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tracked_assignments (
            assignment_id         INTEGER PRIMARY KEY,
            course_id             INTEGER NOT NULL REFERENCES courses(course_id),
            name                  TEXT NOT NULL,
            due_at                TEXT,
            last_notified_urgency TEXT,
            first_seen_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tracked_announcements (
            announcement_id INTEGER PRIMARY KEY,
            course_id       INTEGER NOT NULL REFERENCES courses(course_id),
            title           TEXT NOT NULL,
            notified_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS notification_history (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_type TEXT NOT NULL,
            reference_id      INTEGER NOT NULL,
            course_id         INTEGER NOT NULL,
            message_hash      TEXT NOT NULL,
            sent_at           TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sync_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at      TEXT NOT NULL,
            finished_at     TEXT NOT NULL,
            courses_synced  INTEGER NOT NULL DEFAULT 0,
            files_uploaded  INTEGER NOT NULL DEFAULT 0,
            files_updated   INTEGER NOT NULL DEFAULT 0,
            notifications   INTEGER NOT NULL DEFAULT 0,
            errors_json     TEXT NOT NULL DEFAULT '[]',
            status          TEXT NOT NULL DEFAULT 'ok'
        );

        CREATE INDEX IF NOT EXISTS idx_notification_dedup
            ON notification_history(notification_type, reference_id, message_hash);

        CREATE INDEX IF NOT EXISTS idx_tracked_files_course
            ON tracked_files(course_id);

        CREATE INDEX IF NOT EXISTS idx_tracked_assignments_course
            ON tracked_assignments(course_id);

        CREATE TABLE IF NOT EXISTS user_preferences (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)


# --- Course-Drive mapping ---


def upsert_course(
    conn: sqlite3.Connection,
    course_id: int,
    name: str,
    course_code: str | None = None,
    drive_folder_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO courses (course_id, name, course_code, drive_folder_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(course_id) DO UPDATE SET
            name = excluded.name,
            course_code = excluded.course_code,
            drive_folder_id = COALESCE(excluded.drive_folder_id, courses.drive_folder_id),
            updated_at = datetime('now')
        """,
        (course_id, name, course_code, drive_folder_id),
    )
    conn.commit()


def get_course(conn: sqlite3.Connection, course_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM courses WHERE course_id = ?", (course_id,)).fetchone()
    return dict(row) if row else None


def get_all_courses(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM courses").fetchall()
    return [dict(r) for r in rows]


def set_drive_folder_id(conn: sqlite3.Connection, course_id: int, folder_id: str) -> None:
    conn.execute(
        "UPDATE courses SET drive_folder_id = ?, updated_at = datetime('now') WHERE course_id = ?",
        (folder_id, course_id),
    )
    conn.commit()


# --- File tracking ---


def get_tracked_file(conn: sqlite3.Connection, canvas_file_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM tracked_files WHERE canvas_file_id = ?", (canvas_file_id,)
    ).fetchone()
    return dict(row) if row else None


def upsert_tracked_file(
    conn: sqlite3.Connection,
    canvas_file_id: int,
    course_id: int,
    display_name: str,
    canvas_updated_at: str,
    drive_file_id: str,
    drive_web_link: str,
) -> None:
    conn.execute(
        """
        INSERT INTO tracked_files
            (canvas_file_id, course_id, display_name, canvas_updated_at, drive_file_id, drive_web_link)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(canvas_file_id) DO UPDATE SET
            display_name = excluded.display_name,
            canvas_updated_at = excluded.canvas_updated_at,
            drive_file_id = excluded.drive_file_id,
            drive_web_link = excluded.drive_web_link,
            synced_at = datetime('now')
        """,
        (canvas_file_id, course_id, display_name, canvas_updated_at, drive_file_id, drive_web_link),
    )
    conn.commit()


# --- Assignment tracking ---


def get_tracked_assignment(conn: sqlite3.Connection, assignment_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM tracked_assignments WHERE assignment_id = ?", (assignment_id,)
    ).fetchone()
    return dict(row) if row else None


def upsert_tracked_assignment(
    conn: sqlite3.Connection,
    assignment_id: int,
    course_id: int,
    name: str,
    due_at: str | None,
    last_notified_urgency: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO tracked_assignments
            (assignment_id, course_id, name, due_at, last_notified_urgency)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(assignment_id) DO UPDATE SET
            name = excluded.name,
            due_at = excluded.due_at,
            last_notified_urgency = COALESCE(excluded.last_notified_urgency,
                                             tracked_assignments.last_notified_urgency),
            updated_at = datetime('now')
        """,
        (assignment_id, course_id, name, due_at, last_notified_urgency),
    )
    conn.commit()


# --- Announcement tracking ---


def get_tracked_announcement(conn: sqlite3.Connection, announcement_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM tracked_announcements WHERE announcement_id = ?", (announcement_id,)
    ).fetchone()
    return dict(row) if row else None


def mark_announcement_notified(
    conn: sqlite3.Connection,
    announcement_id: int,
    course_id: int,
    title: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO tracked_announcements (announcement_id, course_id, title)
        VALUES (?, ?, ?)
        """,
        (announcement_id, course_id, title),
    )
    conn.commit()


# --- Notification history ---


def record_notification(
    conn: sqlite3.Connection,
    notification_type: str,
    reference_id: int,
    course_id: int,
    message_hash: str,
) -> None:
    conn.execute(
        """
        INSERT INTO notification_history (notification_type, reference_id, course_id, message_hash)
        VALUES (?, ?, ?, ?)
        """,
        (notification_type, reference_id, course_id, message_hash),
    )
    conn.commit()


def was_notification_sent(
    conn: sqlite3.Connection,
    notification_type: str,
    reference_id: int,
    message_hash: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM notification_history
        WHERE notification_type = ? AND reference_id = ? AND message_hash = ?
        LIMIT 1
        """,
        (notification_type, reference_id, message_hash),
    ).fetchone()
    return row is not None


# --- Sync run history ---


def record_sync_run(
    conn: sqlite3.Connection,
    started_at: str,
    finished_at: str,
    courses_synced: int,
    files_uploaded: int,
    files_updated: int,
    notifications: int,
    errors: list[str],
) -> None:
    status = "error" if errors else "ok"
    conn.execute(
        """
        INSERT INTO sync_runs
            (started_at, finished_at, courses_synced, files_uploaded, files_updated,
             notifications, errors_json, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            started_at,
            finished_at,
            courses_synced,
            files_uploaded,
            files_updated,
            notifications,
            json.dumps(errors),
            status,
        ),
    )
    conn.commit()


# --- User preferences ---


def get_preference(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM user_preferences WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_preference(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO user_preferences (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = datetime('now')
        """,
        (key, value),
    )
    conn.commit()


def get_excluded_course_ids(conn: sqlite3.Connection) -> list[int]:
    raw = get_preference(conn, "excluded_course_ids")
    if raw is None:
        return []
    return json.loads(raw)


def set_excluded_course_ids(conn: sqlite3.Connection, ids: list[int]) -> None:
    set_preference(conn, "excluded_course_ids", json.dumps(ids))


def get_assignments_for_course(conn: sqlite3.Connection, course_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM tracked_assignments WHERE course_id = ? ORDER BY due_at",
        (course_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Sync run history ---


def get_last_sync_run(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["errors"] = json.loads(result.pop("errors_json"))
    return result
