"""Telegram notification formatting and sending."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from canvas_companion.models import (
    CanvasAnnouncement,
    CanvasAssignment,
    CanvasFile,
    NotificationType,
    UrgencyLevel,
)

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LEN = 4096
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def compute_urgency(due_at: datetime | None) -> UrgencyLevel:
    """Determine urgency bucket based on time until deadline."""
    if due_at is None:
        return UrgencyLevel.NORMAL

    # Ensure timezone-aware comparison
    now = datetime.now(timezone.utc)
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)

    delta = due_at - now
    hours = delta.total_seconds() / 3600

    if hours <= 6:
        return UrgencyLevel.CRITICAL
    if hours <= 24:
        return UrgencyLevel.URGENT
    if hours <= 72:
        return UrgencyLevel.UPCOMING
    return UrgencyLevel.NORMAL


def make_notification_hash(
    notification_type: NotificationType,
    reference_id: int,
    **kwargs: str | None,
) -> str:
    """Create a deterministic hash for dedup. kwargs include due_at, urgency, etc."""
    parts = [notification_type.value, str(reference_id)]
    for k in sorted(kwargs):
        parts.append(f"{k}={kwargs[k]}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def urgency_prefix(urgency: UrgencyLevel) -> str:
    match urgency:
        case UrgencyLevel.CRITICAL:
            return "[!!!] "
        case UrgencyLevel.URGENT:
            return "[!!] "
        case UrgencyLevel.UPCOMING:
            return "[!] "
        case _:
            return ""


# Keep old name for any internal callers
_urgency_prefix = urgency_prefix


def format_due(due_at: datetime | None) -> str:
    if due_at is None:
        return "No due date"
    return due_at.strftime("%b %d, %Y %H:%M UTC")


# Keep old name for any internal callers
_format_due = format_due


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id

    async def send_message(self, text: str, parse_mode: str = ParseMode.HTML) -> None:
        """Send a message, splitting if > 4096 chars."""
        chunks = [text[i : i + _MAX_MESSAGE_LEN] for i in range(0, len(text), _MAX_MESSAGE_LEN)]
        for chunk in chunks:
            try:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=chunk,
                    parse_mode=parse_mode,
                )
            except RetryAfter as e:
                logger.warning("Telegram rate limit, retry after %s seconds", e.retry_after)
                await asyncio.sleep(e.retry_after)
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=chunk,
                    parse_mode=parse_mode,
                )
            except TelegramError as e:
                logger.error("Failed to send Telegram message: %s", e)

    async def notify_new_assignment(
        self,
        assignment: CanvasAssignment,
        course_name: str,
        urgency: UrgencyLevel,
    ) -> None:
        prefix = _urgency_prefix(urgency)
        text = (
            f"{prefix}<b>New Assignment</b>\n"
            f"<b>Course:</b> {course_name}\n"
            f"<b>Name:</b> {assignment.name}\n"
            f"<b>Due:</b> {_format_due(assignment.due_at)}\n"
            f"<a href=\"{assignment.html_url}\">View on Canvas</a>"
        )
        await self.send_message(text)

    async def notify_due_date_changed(
        self,
        assignment: CanvasAssignment,
        course_name: str,
        old_due: str | None,
        urgency: UrgencyLevel,
    ) -> None:
        prefix = _urgency_prefix(urgency)
        text = (
            f"{prefix}<b>Due Date Changed</b>\n"
            f"<b>Course:</b> {course_name}\n"
            f"<b>Assignment:</b> {assignment.name}\n"
            f"<b>Old due:</b> {old_due or 'None'}\n"
            f"<b>New due:</b> {_format_due(assignment.due_at)}\n"
            f"<a href=\"{assignment.html_url}\">View on Canvas</a>"
        )
        await self.send_message(text)

    async def notify_new_announcement(
        self,
        announcement: CanvasAnnouncement,
        course_name: str,
    ) -> None:
        # Strip HTML tags from Canvas announcement body, then truncate
        body = _HTML_TAG_RE.sub("", announcement.message).strip()
        if len(body) > 500:
            body = body[:500] + "..."
        text = (
            f"<b>New Announcement</b>\n"
            f"<b>Course:</b> {course_name}\n"
            f"<b>Title:</b> {announcement.title}\n\n"
            f"{body}"
        )
        await self.send_message(text)

    async def notify_file_synced(
        self,
        file: CanvasFile,
        course_name: str,
        drive_link: str,
        is_update: bool,
    ) -> None:
        action = "Updated" if is_update else "New"
        text = (
            f"<b>{action} File Synced</b>\n"
            f"<b>Course:</b> {course_name}\n"
            f"<b>File:</b> {file.display_name}\n"
            f"<a href=\"{drive_link}\">Open in Google Drive</a>"
        )
        await self.send_message(text)

    async def notify_deadline_reminder(
        self,
        assignment: CanvasAssignment,
        course_name: str,
        urgency: UrgencyLevel,
    ) -> None:
        prefix = _urgency_prefix(urgency)
        text = (
            f"{prefix}<b>Deadline Reminder</b>\n"
            f"<b>Course:</b> {course_name}\n"
            f"<b>Assignment:</b> {assignment.name}\n"
            f"<b>Due:</b> {_format_due(assignment.due_at)}\n"
            f"<a href=\"{assignment.html_url}\">View on Canvas</a>"
        )
        await self.send_message(text)
