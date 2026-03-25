"""Shared test fixtures."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from canvas_companion.config import Settings
from canvas_companion.db import init_schema

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "canvas"


@pytest.fixture
def db_conn():
    """In-memory SQLite with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def settings(monkeypatch):
    """Settings with all required values set via env."""
    monkeypatch.setenv("CC_CANVAS_BASE_URL", "https://canvas.test.edu")
    monkeypatch.setenv("CC_CANVAS_API_TOKEN", "test_token")
    monkeypatch.setenv("CC_TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("CC_TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setenv("CC_DB_PATH", ":memory:")
    return Settings()  # type: ignore[call-arg]


def load_fixture(name: str) -> list[dict]:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES_DIR / name).read_text())
