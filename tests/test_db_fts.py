"""Tests for FTS5 file_chunks and prep_sessions in db.py."""

from __future__ import annotations

from canvas_companion import db


def test_file_chunks_table_exists(db_conn):
    """FTS5 virtual table should be created by init_schema."""
    row = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='file_chunks'"
    ).fetchone()
    assert row is not None


def test_prep_sessions_table_exists(db_conn):
    row = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prep_sessions'"
    ).fetchone()
    assert row is not None


def test_upsert_file_chunks(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    chunks = ["chunk zero", "chunk one", "chunk two"]
    db.upsert_file_chunks(db_conn, 9001, 101, chunks)

    rows = db_conn.execute("SELECT * FROM file_chunks").fetchall()
    assert len(rows) == 3


def test_upsert_replaces_existing(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.upsert_file_chunks(db_conn, 9001, 101, ["old chunk"])
    db.upsert_file_chunks(db_conn, 9001, 101, ["new chunk A", "new chunk B"])

    rows = db_conn.execute("SELECT * FROM file_chunks").fetchall()
    assert len(rows) == 2
    contents = [r["content"] for r in rows]
    assert "old chunk" not in contents
    assert "new chunk A" in contents


def test_search_chunks_returns_results(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.upsert_file_chunks(db_conn, 9001, 101, [
        "Introduction to algorithms and data structures",
        "Advanced topics in machine learning",
    ])

    results = db.search_chunks(db_conn, 101, "algorithms")
    assert len(results) >= 1
    assert "algorithms" in results[0]["content"]


def test_search_chunks_filters_by_course(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    db.upsert_course(db_conn, 202, "CS202", "CS202")
    db.upsert_file_chunks(db_conn, 9001, 101, ["algorithms for CS101"])
    db.upsert_file_chunks(db_conn, 9002, 202, ["algorithms for CS202"])

    results = db.search_chunks(db_conn, 101, "algorithms")
    assert all(r["course_id"] == "101" for r in results)


def test_has_file_chunks(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    assert db.has_file_chunks(db_conn, 9001) is False

    db.upsert_file_chunks(db_conn, 9001, 101, ["some content"])
    assert db.has_file_chunks(db_conn, 9001) is True


def test_record_prep_session(db_conn):
    db.upsert_course(db_conn, 101, "CS101", "CS101")
    session_id = db.record_prep_session(
        db_conn, 101, "quiz", "Chapters 1-3",
        "2026-04-01T10:00:00", "study pack text", "cal_event_123",
    )
    assert session_id is not None
    assert session_id > 0

    row = db_conn.execute(
        "SELECT * FROM prep_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    assert row is not None
    assert row["prep_type"] == "quiz"
    assert row["scope"] == "Chapters 1-3"
    assert row["calendar_event_id"] == "cal_event_123"
