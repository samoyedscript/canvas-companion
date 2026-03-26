"""Core sync orchestrator — executes a single, complete sync run."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from canvas_companion import db
from canvas_companion.canvas_api import CanvasClient
from canvas_companion.drive_sync import DriveSync
from canvas_companion.models import (
    CanvasAssignment,
    CanvasFile,
    NotificationType,
    SyncResult,
    UrgencyLevel,
    URGENCY_RANK,
)
from canvas_companion.telegram_notifier import (
    TelegramNotifier,
    compute_urgency,
    make_notification_hash,
)

logger = logging.getLogger(__name__)


async def _process_assignment(
    assignment: CanvasAssignment,
    course_name: str,
    conn: sqlite3.Connection,
    notifier: TelegramNotifier,
) -> bool:
    """Handle a single assignment. Return True if a notification was sent."""
    tracked = db.get_tracked_assignment(conn, assignment.id)
    urgency = compute_urgency(assignment.due_at)
    due_at_str = assignment.due_at.isoformat() if assignment.due_at else None

    if tracked is None:
        await notifier.notify_new_assignment(assignment, course_name, urgency)
        db.upsert_tracked_assignment(
            conn, assignment.id, assignment.course_id, assignment.name,
            due_at_str, urgency.value,
        )
        db.record_notification(
            conn, NotificationType.NEW_ASSIGNMENT.value, assignment.id,
            assignment.course_id,
            make_notification_hash(NotificationType.NEW_ASSIGNMENT, assignment.id),
        )
        return True

    if tracked["due_at"] != due_at_str:
        await notifier.notify_due_date_changed(
            assignment, course_name, tracked["due_at"], urgency,
        )
        db.upsert_tracked_assignment(
            conn, assignment.id, assignment.course_id, assignment.name,
            due_at_str, urgency.value,
        )
        db.record_notification(
            conn, NotificationType.DUE_DATE_CHANGED.value, assignment.id,
            assignment.course_id,
            make_notification_hash(
                NotificationType.DUE_DATE_CHANGED, assignment.id, due_at=due_at_str,
            ),
        )
        return True

    if (
        assignment.due_at is not None
        and urgency != UrgencyLevel.NORMAL
        and tracked["last_notified_urgency"] is not None
    ):
        prev_urgency = UrgencyLevel(tracked["last_notified_urgency"])
        if URGENCY_RANK[urgency] > URGENCY_RANK[prev_urgency]:
            await notifier.notify_deadline_reminder(assignment, course_name, urgency)
            db.upsert_tracked_assignment(
                conn, assignment.id, assignment.course_id, assignment.name,
                due_at_str, urgency.value,
            )
            db.record_notification(
                conn, NotificationType.DEADLINE_REMINDER.value, assignment.id,
                assignment.course_id,
                make_notification_hash(
                    NotificationType.DEADLINE_REMINDER, assignment.id,
                    urgency=urgency.value,
                ),
            )
            return True

    return False


def _is_pdf(file: CanvasFile) -> bool:
    return (file.content_type == "application/pdf"
            or file.display_name.lower().endswith(".pdf"))


def _index_pdf(file_id: int, course_id: int, content: bytes,
               conn: sqlite3.Connection) -> None:
    """Extract text from a PDF and store chunks in FTS."""
    from canvas_companion.pdf_extract import extract_and_chunk
    try:
        chunks = extract_and_chunk(content)
        if chunks:
            db.upsert_file_chunks(conn, file_id, course_id, chunks)
            logger.info("Indexed %d chunks from file %d", len(chunks), file_id)
    except Exception as e:
        logger.warning("PDF text extraction failed for file %d: %s", file_id, e)


async def _process_file(
    file: CanvasFile,
    course_name: str,
    folder_id: str,
    conn: sqlite3.Connection,
    canvas: CanvasClient,
    drive: DriveSync,
    notifier: TelegramNotifier,
) -> tuple[int, int, int]:
    """Handle a single file. Return (uploaded, updated, notifications)."""
    tracked = db.get_tracked_file(conn, file.id)
    updated_at_str = file.updated_at.isoformat()

    if tracked is None:
        content = await canvas.download_file(file.url)
        drive_id, link = drive.upload_file(
            file.display_name, content, file.content_type, folder_id,
        )
        db.upsert_tracked_file(
            conn, file.id, file.course_id, file.display_name,
            updated_at_str, drive_id, link,
        )
        if _is_pdf(file):
            _index_pdf(file.id, file.course_id, content, conn)
        await notifier.notify_file_synced(file, course_name, link, is_update=False)
        return 1, 0, 1

    if tracked["canvas_updated_at"] != updated_at_str:
        content = await canvas.download_file(file.url)
        drive_id, link = drive.update_file(
            tracked["drive_file_id"], file.display_name, content, file.content_type,
        )
        db.upsert_tracked_file(
            conn, file.id, file.course_id, file.display_name,
            updated_at_str, drive_id, link,
        )
        if _is_pdf(file):
            _index_pdf(file.id, file.course_id, content, conn)
        await notifier.notify_file_synced(file, course_name, link, is_update=True)
        return 0, 1, 1

    # File unchanged — backfill FTS if needed
    if _is_pdf(file) and not db.has_file_chunks(conn, file.id):
        try:
            content = await canvas.download_file(file.url)
            _index_pdf(file.id, file.course_id, content, conn)
        except Exception as e:
            logger.warning("Backfill indexing failed for '%s': %s", file.display_name, e)

    return 0, 0, 0


async def run_sync(
    canvas: CanvasClient,
    drive: DriveSync,
    notifier: TelegramNotifier,
    conn: sqlite3.Connection,
) -> SyncResult:
    """Execute one complete sync cycle."""
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []
    files_uploaded = 0
    files_updated = 0
    notifications_sent = 0

    # 1. Fetch active courses
    try:
        courses = await canvas.get_active_courses()
    except Exception as e:
        logger.error("Failed to fetch courses: %s", e)
        finished_at = datetime.now(timezone.utc)
        result = SyncResult(
            started_at=started_at,
            finished_at=finished_at,
            courses_synced=0,
            files_uploaded=0,
            files_updated=0,
            notifications_sent=0,
            errors=[f"Failed to fetch courses: {e}"],
        )
        db.record_sync_run(
            conn, started_at.isoformat(), finished_at.isoformat(),
            0, 0, 0, 0, result.errors,
        )
        return result

    for course in courses:
        db.upsert_course(conn, course.id, course.name, course.course_code)

    # Filter out user-excluded courses (upsert above keeps all courses visible)
    excluded_ids = set(db.get_excluded_course_ids(conn))
    active_courses = [c for c in courses if c.id not in excluded_ids]

    course_names = {c.id: c.name for c in active_courses}

    # 2. Fetch all announcements in one API call
    all_announcements = await canvas.get_announcements([c.id for c in active_courses])
    announcements_by_course: dict[int, list] = {}
    for announcement in all_announcements:
        announcements_by_course.setdefault(announcement.course_id, []).append(announcement)

    # 3. Process each course independently
    for course in active_courses:
        try:
            root_id = drive.ensure_root_folder()
            folder_id = drive.ensure_course_folder(course.name, root_id)
            db.set_drive_folder_id(conn, course.id, folder_id)

            # Assignments
            assignments = await canvas.get_assignments(course.id)
            for assignment in assignments:
                if await _process_assignment(assignment, course.name, conn, notifier):
                    notifications_sent += 1

            # Announcements
            for announcement in announcements_by_course.get(course.id, []):
                if db.get_tracked_announcement(conn, announcement.id) is None:
                    await notifier.notify_new_announcement(announcement, course.name)
                    db.mark_announcement_notified(
                        conn, announcement.id, course.id, announcement.title,
                    )
                    db.record_notification(
                        conn, NotificationType.NEW_ANNOUNCEMENT.value, announcement.id,
                        course.id,
                        make_notification_hash(
                            NotificationType.NEW_ANNOUNCEMENT, announcement.id,
                        ),
                    )
                    notifications_sent += 1

            # Files
            canvas_files = await canvas.get_files(course.id)
            for file in canvas_files:
                uploaded, updated, notified = await _process_file(
                    file, course.name, folder_id, conn, canvas, drive, notifier,
                )
                files_uploaded += uploaded
                files_updated += updated
                notifications_sent += notified

        except Exception as e:
            error_msg = f"Error processing course '{course.name}' (id={course.id}): {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    # 4. Record sync run
    finished_at = datetime.now(timezone.utc)
    result = SyncResult(
        started_at=started_at,
        finished_at=finished_at,
        courses_synced=len(active_courses),
        files_uploaded=files_uploaded,
        files_updated=files_updated,
        notifications_sent=notifications_sent,
        errors=errors,
    )
    db.record_sync_run(
        conn, started_at.isoformat(), finished_at.isoformat(),
        len(active_courses), files_uploaded, files_updated, notifications_sent, errors,
    )
    return result
