"""Tests for calendar_service.py."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from canvas_companion.calendar_service import CalendarService


def test_create_event():
    mock_creds = MagicMock()
    with patch("canvas_companion.calendar_service.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.events.return_value.insert.return_value.execute.return_value = {
            "id": "event_123",
            "htmlLink": "https://calendar.google.com/event/123",
        }

        cal = CalendarService(mock_creds)
        result = cal.create_event(
            summary="Prep - CS101",
            description="Study pack text",
            start_time=datetime(2026, 4, 1, 10, 0),
            end_time=datetime(2026, 4, 1, 12, 0),
        )

        assert result["id"] == "event_123"
        mock_service.events.return_value.insert.assert_called_once()
        call_kwargs = mock_service.events.return_value.insert.call_args
        assert call_kwargs.kwargs["calendarId"] == "primary"
        body = call_kwargs.kwargs["body"]
        assert body["summary"] == "Prep - CS101"
        assert body["start"]["timeZone"] == "Asia/Singapore"


def test_check_connectivity_success():
    mock_creds = MagicMock()
    with patch("canvas_companion.calendar_service.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        cal = CalendarService(mock_creds)
        assert cal.check_connectivity() is True
        mock_service.calendarList.return_value.get.assert_called_once()


def test_check_connectivity_failure():
    mock_creds = MagicMock()
    with patch("canvas_companion.calendar_service.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.calendarList.return_value.get.return_value.execute.side_effect = (
            Exception("Not authorized")
        )

        cal = CalendarService(mock_creds)
        assert cal.check_connectivity() is False
