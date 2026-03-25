"""Tests for nus_calendar.py."""

from __future__ import annotations

from datetime import date

from canvas_companion.nus_calendar import format_start_message, get_current_period


def test_sem1_orientation_week():
    result = get_current_period(date(2025, 8, 5))
    assert result is not None
    semester, label, week = result
    assert semester == "Semester 1"
    assert label == "Orientation Week"
    assert week is None


def test_sem1_week1():
    result = get_current_period(date(2025, 8, 12))
    assert result is not None
    semester, label, week = result
    assert semester == "Semester 1"
    assert label == "Week 1"
    assert week == 1


def test_sem1_recess_week():
    result = get_current_period(date(2025, 9, 22))
    assert result is not None
    semester, label, week = result
    assert semester == "Semester 1"
    assert label == "Recess Week"
    assert week is None


def test_sem1_week13():
    result = get_current_period(date(2025, 11, 11))
    assert result is not None
    _, label, week = result
    assert label == "Week 13"
    assert week == 13


def test_sem1_reading_week():
    result = get_current_period(date(2025, 11, 17))
    assert result is not None
    _, label, week = result
    assert label == "Reading Week"
    assert week is None


def test_sem1_examination():
    result = get_current_period(date(2025, 11, 25))
    assert result is not None
    _, label, _ = result
    assert label == "Examination"


def test_sem1_vacation():
    result = get_current_period(date(2025, 12, 20))
    assert result is not None
    _, label, _ = result
    assert label == "Vacation"


def test_sem2_week1():
    result = get_current_period(date(2026, 1, 14))
    assert result is not None
    semester, label, week = result
    assert semester == "Semester 2"
    assert label == "Week 1"
    assert week == 1


def test_sem2_recess_week():
    result = get_current_period(date(2026, 2, 25))
    assert result is not None
    _, label, _ = result
    assert label == "Recess Week"


def test_sem2_week10():
    result = get_current_period(date(2026, 3, 25))
    assert result is not None
    semester, label, week = result
    assert semester == "Semester 2"
    assert label == "Week 10"
    assert week == 10


def test_sem2_examination():
    result = get_current_period(date(2026, 5, 1))
    assert result is not None
    _, label, _ = result
    assert label == "Examination"


def test_special_term_1():
    result = get_current_period(date(2026, 6, 1))
    assert result is not None
    semester, label, _ = result
    assert semester == "Special Term I"
    assert label == "Instructional Period"


def test_special_term_2():
    result = get_current_period(date(2026, 7, 1))
    assert result is not None
    semester, label, _ = result
    assert semester == "Special Term II"


def test_outside_ay_returns_none():
    result = get_current_period(date(2026, 8, 15))
    assert result is None


def test_format_start_message_instructional():
    msg = format_start_message(date(2026, 3, 25))
    assert "AY2025-2026" in msg
    assert "Semester 2" in msg
    assert "Week 10" in msg
    assert "Instructional" in msg


def test_format_start_message_non_instructional():
    msg = format_start_message(date(2025, 9, 22))
    assert "Recess Week" in msg
    assert "Instructional" not in msg


def test_format_start_message_outside_ay():
    msg = format_start_message(date(2026, 8, 15))
    assert "No active semester period" in msg


def test_boundary_first_day_of_sem1():
    result = get_current_period(date(2025, 8, 4))
    assert result is not None
    _, label, _ = result
    assert label == "Orientation Week"


def test_boundary_last_day_of_sem2_vacation():
    # Semester 2 vacation is just May 10 — the Sunday between exams and Special Term I
    result = get_current_period(date(2026, 5, 10))
    assert result is not None
    _, label, _ = result
    assert label == "Vacation"


def test_summer_after_special_terms_is_outside_ay():
    # Aug 2 is the last day of Special Term II; Aug 3+ is outside AY2025-2026
    result = get_current_period(date(2026, 8, 2))
    assert result is None
