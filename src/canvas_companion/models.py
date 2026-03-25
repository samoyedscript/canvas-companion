"""Shared data models for Canvas entities, notification types, and sync results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class CanvasCourse(BaseModel):
    id: int
    name: str
    course_code: str


class CanvasAssignment(BaseModel):
    id: int
    course_id: int
    name: str
    description: str | None = None
    due_at: datetime | None = None
    html_url: str
    points_possible: float | None = None


class CanvasAnnouncement(BaseModel):
    id: int
    course_id: int
    title: str
    message: str
    posted_at: datetime


class CanvasSubmission(BaseModel):
    assignment_id: int
    workflow_state: str = "unsubmitted"
    submitted_at: str | None = None
    late: bool = False
    missing: bool = False


class CanvasFile(BaseModel):
    id: int
    course_id: int
    display_name: str
    url: str
    updated_at: datetime
    size: int
    content_type: str | None = None


class UrgencyLevel(str, Enum):
    NORMAL = "normal"
    UPCOMING = "upcoming"
    URGENT = "urgent"
    CRITICAL = "critical"

URGENCY_RANK: dict[UrgencyLevel, int] = {
    UrgencyLevel.NORMAL: 0,
    UrgencyLevel.UPCOMING: 1,
    UrgencyLevel.URGENT: 2,
    UrgencyLevel.CRITICAL: 3,
}


class NotificationType(str, Enum):
    NEW_ASSIGNMENT = "new_assignment"
    DUE_DATE_CHANGED = "due_date_changed"
    NEW_ANNOUNCEMENT = "new_announcement"
    NEW_FILE = "new_file"
    UPDATED_FILE = "updated_file"
    DEADLINE_REMINDER = "deadline_reminder"


class SyncResult(BaseModel):
    started_at: datetime
    finished_at: datetime
    courses_synced: int
    files_uploaded: int
    files_updated: int
    notifications_sent: int
    errors: list[str]
