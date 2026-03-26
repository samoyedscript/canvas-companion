"""Tests for prep_handler.py conversation flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from canvas_companion import db
from canvas_companion.prep_handler import (
    AWAITING_APPROVAL,
    ENTERING_DATETIME,
    ENTERING_FILE_NAME,
    ENTERING_QUIZ_NAME,
    SELECTING_COURSE,
    SELECTING_PREP_TYPE,
    create_prep_conversation,
)
from telegram.ext import ConversationHandler, filters


@pytest.fixture
def seeded_db(db_conn):
    """DB with courses for testing."""
    db.upsert_course(db_conn, 101, "CS101 Data Structures", "CS101")
    db.upsert_course(db_conn, 202, "CS202 Algorithms", "CS202")
    return db_conn


def test_create_prep_conversation_returns_handler(seeded_db):
    """ConversationHandler should be created successfully."""
    handler = create_prep_conversation(
        chat_filter=filters.ALL,
        conn=seeded_db,
        gemini=MagicMock(),
        calendar=MagicMock(),
    )
    assert isinstance(handler, ConversationHandler)


def test_conversation_has_correct_states(seeded_db):
    handler = create_prep_conversation(
        chat_filter=filters.ALL,
        conn=seeded_db,
        gemini=MagicMock(),
        calendar=MagicMock(),
    )
    assert SELECTING_COURSE in handler.states
    assert SELECTING_PREP_TYPE in handler.states
    assert ENTERING_QUIZ_NAME in handler.states
    assert ENTERING_FILE_NAME in handler.states
    assert AWAITING_APPROVAL in handler.states
    assert ENTERING_DATETIME in handler.states


def test_state_constants():
    """State constants should be sequential integers."""
    assert SELECTING_COURSE == 0
    assert SELECTING_PREP_TYPE == 1
    assert ENTERING_QUIZ_NAME == 2
    assert ENTERING_FILE_NAME == 3
    assert AWAITING_APPROVAL == 4
    assert ENTERING_DATETIME == 5


def test_conversation_has_two_entry_points(seeded_db):
    """ConversationHandler should accept both /prep command and prep_start callback."""
    from telegram.ext import CallbackQueryHandler, CommandHandler

    handler = create_prep_conversation(
        chat_filter=filters.ALL,
        conn=seeded_db,
        gemini=MagicMock(),
        calendar=MagicMock(),
    )
    entry_types = {type(ep) for ep in handler.entry_points}
    assert CommandHandler in entry_types
    assert CallbackQueryHandler in entry_types
