"""Tests for telegram_notifier.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from canvas_companion.models import (
    CanvasAnnouncement,
    CanvasAssignment,
    CanvasFile,
    NotificationType,
    UrgencyLevel,
)
from canvas_companion.telegram_notifier import (
    compute_urgency,
    make_notification_hash,
)


def test_compute_urgency_normal():
    due = datetime.now(timezone.utc) + timedelta(days=5)
    assert compute_urgency(due) == UrgencyLevel.NORMAL


def test_compute_urgency_upcoming():
    due = datetime.now(timezone.utc) + timedelta(hours=48)
    assert compute_urgency(due) == UrgencyLevel.UPCOMING


def test_compute_urgency_urgent():
    due = datetime.now(timezone.utc) + timedelta(hours=12)
    assert compute_urgency(due) == UrgencyLevel.URGENT


def test_compute_urgency_critical():
    due = datetime.now(timezone.utc) + timedelta(hours=3)
    assert compute_urgency(due) == UrgencyLevel.CRITICAL


def test_compute_urgency_past_deadline():
    due = datetime.now(timezone.utc) - timedelta(hours=1)
    assert compute_urgency(due) == UrgencyLevel.CRITICAL


def test_compute_urgency_none():
    assert compute_urgency(None) == UrgencyLevel.NORMAL


def test_compute_urgency_naive_datetime():
    """Naive datetimes should be treated as UTC."""
    due = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)
    assert compute_urgency(due) == UrgencyLevel.CRITICAL


def test_notification_hash_deterministic():
    h1 = make_notification_hash(NotificationType.NEW_ASSIGNMENT, 1001)
    h2 = make_notification_hash(NotificationType.NEW_ASSIGNMENT, 1001)
    assert h1 == h2


def test_notification_hash_different_types():
    h1 = make_notification_hash(NotificationType.NEW_ASSIGNMENT, 1001)
    h2 = make_notification_hash(NotificationType.DUE_DATE_CHANGED, 1001)
    assert h1 != h2


def test_notification_hash_with_kwargs():
    h1 = make_notification_hash(
        NotificationType.DUE_DATE_CHANGED, 1001, due_at="2026-04-01"
    )
    h2 = make_notification_hash(
        NotificationType.DUE_DATE_CHANGED, 1001, due_at="2026-04-15"
    )
    assert h1 != h2
