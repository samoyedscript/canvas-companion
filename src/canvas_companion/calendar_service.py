"""Google Calendar API wrapper for creating study events."""

from __future__ import annotations

import logging
from datetime import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class CalendarService:
    def __init__(self, credentials: Credentials) -> None:
        self._service = build("calendar", "v3", credentials=credentials)

    def create_event(
        self,
        summary: str,
        description: str,
        start_time: datetime,
        end_time: datetime,
        timezone: str = "Asia/Singapore",
    ) -> dict:
        """Create a Google Calendar event. Returns the event resource."""
        event_body = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": timezone,
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 30},
                ],
            },
        }
        result = self._service.events().insert(
            calendarId="primary", body=event_body,
        ).execute()
        logger.info("Created calendar event: %s (id=%s)", summary, result["id"])
        return result

    def check_connectivity(self) -> bool:
        """Test Calendar API access."""
        try:
            self._service.events().list(calendarId="primary", maxResults=1).execute()
            return True
        except Exception as e:
            logger.warning("Calendar connectivity check failed: %s", e)
            return False
