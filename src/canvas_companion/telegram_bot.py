"""Telegram bot command handlers and interactive inline-keyboard UI."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

from canvas_companion import db
from canvas_companion.canvas_api import CanvasClient
from canvas_companion.nus_calendar import format_start_message
from canvas_companion.scheduler import SyncScheduler
from canvas_companion.telegram_notifier import compute_urgency, urgency_prefix, format_due

logger = logging.getLogger(__name__)

_ASSIGNMENTS_PER_PAGE = 5
_COURSES_PER_PAGE = 8

_FREQ_OPTIONS = [
    (5, "5 min"),
    (30, "30 min"),
    (240, "4 hours"),
    (720, "12 hours"),
    (1440, "1 day"),
    (10080, "1 week"),
]


def _format_interval(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 1440:
        h = minutes // 60
        return f"{h} hour{'s' if h > 1 else ''}"
    d = minutes // 1440
    return f"{d} day{'s' if d > 1 else ''}"


def _back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("<< Home", callback_data="home")]])


def _format_sync_result(result) -> str:
    lines = [
        "Sync complete!",
        f"Courses: {result.courses_synced}",
        f"Files uploaded: {result.files_uploaded}",
        f"Files updated: {result.files_updated}",
        f"Notifications: {result.notifications_sent}",
        f"Errors: {len(result.errors)}",
    ]
    return "\n".join(lines)


def _freq_keyboard(current_minutes: int) -> tuple[str, InlineKeyboardMarkup]:
    text = f"Current sync interval: <b>every {_format_interval(current_minutes)}</b>"
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for mins, label in _FREQ_OPTIONS:
        row.append(InlineKeyboardButton(label, callback_data=f"fs:{mins}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("<< Home", callback_data="home")])
    return text, InlineKeyboardMarkup(buttons)


async def _build_outstanding_text(
    active_courses: list[dict],
    canvas: CanvasClient,
    conn: sqlite3.Connection,
) -> str:
    """Fetch submission status for all active courses and return formatted HTML."""
    now = datetime.now(timezone.utc)
    upcoming: list[tuple[str, str, datetime | None, str]] = []
    overdue: list[tuple[str, str, datetime | None]] = []

    for c in active_courses:
        assignments = db.get_assignments_for_course(conn, c["course_id"])
        if not assignments:
            continue

        aid_list = [a["assignment_id"] for a in assignments]
        try:
            subs = await canvas.get_my_submissions(c["course_id"], aid_list)
        except Exception as e:
            logger.warning("Submissions fetch failed for %s: %s", c["name"], e)
            continue

        submitted_ids = {
            s.assignment_id for s in subs
            if s.workflow_state in ("submitted", "graded") or s.submitted_at is not None
        }

        for a in assignments:
            if a["assignment_id"] in submitted_ids:
                continue
            due_dt = datetime.fromisoformat(a["due_at"]) if a["due_at"] else None
            if due_dt and due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            if due_dt is not None and due_dt < now:
                overdue.append((c["name"], a["name"], due_dt))
            else:
                prefix = urgency_prefix(compute_urgency(due_dt))
                upcoming.append((c["name"], a["name"], due_dt, prefix))

    upcoming.sort(key=lambda x: x[2] or datetime.max.replace(tzinfo=timezone.utc))
    overdue.sort(key=lambda x: x[2] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    total = len(upcoming) + len(overdue)
    if total == 0:
        return "All caught up! No outstanding assignments."

    lines = [f"<b>Outstanding Assignments ({total})</b>\n"]
    if upcoming:
        lines.append("<b>Upcoming</b>")
        cur = ""
        for course, name, due_dt, prefix in upcoming:
            if course != cur:
                lines.append(f"\n<b>{course}</b>:")
                cur = course
            lines.append(f"  {prefix}{name} — {format_due(due_dt)}")
    if overdue:
        lines.append("\n<b>Overdue</b>")
        cur = ""
        for course, name, due_dt in overdue:
            if course != cur:
                lines.append(f"\n<b>{course}</b>:")
                cur = course
            lines.append(f"  {name} — {format_due(due_dt)}")

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    return text


def create_bot_application(
    bot_token: str,
    chat_id: str,
    sync_callback: Callable[[], Coroutine[Any, Any, Any]],
    status_callback: Callable[[], dict | None],
    conn: sqlite3.Connection,
    canvas: CanvasClient,
    scheduler: SyncScheduler,
) -> Application:
    """Build and configure the Telegram bot Application."""
    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            ("start", "Home screen with academic calendar"),
            ("courses", "Browse your courses"),
            ("outstanding", "Check unsubmitted assignments"),
            ("frequency", "Change sync interval"),
            ("sync", "Run sync now"),
            ("status", "Last sync status"),
        ])

    app = Application.builder().token(bot_token).post_init(post_init).build()
    chat_filter = filters.Chat(chat_id=int(chat_id))
    chat_id_int = int(chat_id)

    # Store shared state for callback handlers
    app.bot_data["conn"] = conn
    app.bot_data["canvas"] = canvas
    app.bot_data["scheduler"] = scheduler
    app.bot_data["sync_callback"] = sync_callback

    # ── helpers ────────────────────────────────────────────────────────

    def _home_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Courses", callback_data="courses:0")],
            [InlineKeyboardButton("Outstanding Assignments", callback_data="outstanding")],
            [InlineKeyboardButton("Sync Now", callback_data="do_sync")],
            [InlineKeyboardButton("Sync Frequency", callback_data="freq")],
            [InlineKeyboardButton("Sync Status", callback_data="status")],
        ])

    def _courses_keyboard(page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
        all_courses = db.get_all_courses(conn)
        if not all_courses:
            return "No courses synced yet. Run /sync first.", InlineKeyboardMarkup(
                [[InlineKeyboardButton("<< Home", callback_data="home")]]
            )

        excluded = set(db.get_excluded_course_ids(conn))
        total_pages = (len(all_courses) + _COURSES_PER_PAGE - 1) // _COURSES_PER_PAGE
        page = max(0, min(page, total_pages - 1))
        start = page * _COURSES_PER_PAGE
        page_courses = all_courses[start : start + _COURSES_PER_PAGE]

        text_lines = ["<b>Your Courses</b>\n"]
        buttons: list[list[InlineKeyboardButton]] = []
        for c in page_courses:
            status = "✗" if c["course_id"] in excluded else "✓"
            label = f"{status} {c['course_code'] or c['name']}"
            text_lines.append(f"  {status} {c['name']}")
            buttons.append([InlineKeyboardButton(label, callback_data=f"cd:{c['course_id']}")])

        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("< Prev", callback_data=f"courses:{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next >", callback_data=f"courses:{page + 1}"))
        if nav:
            buttons.append(nav)

        buttons.append([
            InlineKeyboardButton("Filter Courses", callback_data="filter"),
            InlineKeyboardButton("<< Home", callback_data="home"),
        ])

        return "\n".join(text_lines), InlineKeyboardMarkup(buttons)

    def _filter_keyboard() -> tuple[str, InlineKeyboardMarkup]:
        all_courses = db.get_all_courses(conn)
        excluded = set(db.get_excluded_course_ids(conn))

        text = "<b>Toggle courses on/off</b>\nIncluded courses sync files &amp; send notifications.\n"
        buttons: list[list[InlineKeyboardButton]] = []
        for c in all_courses:
            is_excluded = c["course_id"] in excluded
            icon = "✗" if is_excluded else "✓"
            state = "OFF" if is_excluded else "ON"
            label = f"{icon} [{state}] {c['course_code'] or c['name']}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"ft:{c['course_id']}")])

        buttons.append([InlineKeyboardButton("Done", callback_data="filter_done")])
        return text, InlineKeyboardMarkup(buttons)

    def _course_detail_text(course_id: int, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
        course = db.get_course(conn, course_id)
        assignments = db.get_assignments_for_course(conn, course_id)
        name = course["name"] if course else f"Course {course_id}"

        if not assignments:
            text = f"<b>{name}</b>\n\nNo assignments tracked yet."
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("<< Courses", callback_data="courses:0")]]
            )
            return text, kb

        total_pages = (len(assignments) + _ASSIGNMENTS_PER_PAGE - 1) // _ASSIGNMENTS_PER_PAGE
        page = max(0, min(page, total_pages - 1))
        start = page * _ASSIGNMENTS_PER_PAGE
        page_assignments = assignments[start : start + _ASSIGNMENTS_PER_PAGE]

        lines = [f"<b>{name}</b> — Assignments\n"]
        for i, a in enumerate(page_assignments, start=start + 1):
            due_str = format_due(
                datetime.fromisoformat(a["due_at"]) if a["due_at"] else None
            )
            lines.append(f"  {i}. {a['name']}\n      Due: {due_str}")

        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("< Prev", callback_data=f"cdp:{course_id}:{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next >", callback_data=f"cdp:{course_id}:{page + 1}"))

        buttons: list[list[InlineKeyboardButton]] = []
        if nav:
            buttons.append(nav)
        buttons.append([InlineKeyboardButton("<< Courses", callback_data="courses:0")])

        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    # ── command handlers ──────────────────────────────────────────────

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = format_start_message()
        await update.message.reply_text(  # type: ignore[union-attr]
            text, parse_mode="HTML", reply_markup=_home_keyboard(),
        )

    async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Starting sync...")  # type: ignore[union-attr]
        try:
            result = await sync_callback()
            await update.message.reply_text(_format_sync_result(result))  # type: ignore[union-attr]
        except Exception as e:
            logger.error("Sync via /sync command failed: %s", e)
            await update.message.reply_text(f"Sync failed: {e}")  # type: ignore[union-attr]

    async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        last_run = status_callback()
        if last_run is None:
            await update.message.reply_text("No sync has been run yet.")  # type: ignore[union-attr]
            return
        error_count = len(last_run.get("errors", []))
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Last sync: {last_run['started_at']}\n"
            f"Status: {last_run['status']}\n"
            f"Courses: {last_run['courses_synced']}\n"
            f"Files uploaded: {last_run['files_uploaded']}\n"
            f"Files updated: {last_run['files_updated']}\n"
            f"Notifications: {last_run['notifications']}\n"
            f"Errors: {error_count}"
        )

    async def cmd_courses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text, kb = _courses_keyboard()
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)  # type: ignore[union-attr]

    async def cmd_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text, kb = _freq_keyboard(scheduler.interval_minutes)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)  # type: ignore[union-attr]

    async def cmd_outstanding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = await update.message.reply_text("Checking submissions...")  # type: ignore[union-attr]
        all_courses = db.get_all_courses(conn)
        excluded = set(db.get_excluded_course_ids(conn))
        active = [c for c in all_courses if c["course_id"] not in excluded]
        text = await _build_outstanding_text(active, canvas, conn)
        try:
            await msg.edit_text(text, parse_mode="HTML")
        except BadRequest:
            await msg.edit_text(text)

    # ── callback query handler ────────────────────────────────────────

    async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        # Verify chat authorization
        if query.from_user and query.from_user.id != chat_id_int:
            await query.answer("Unauthorized", show_alert=True)
            return

        await query.answer()
        data = query.data or ""

        try:
            if data == "home":
                text = format_start_message()
                await query.edit_message_text(
                    text, parse_mode="HTML", reply_markup=_home_keyboard(),
                )

            elif data.startswith("courses:"):
                page = int(data.split(":")[1])
                text, kb = _courses_keyboard(page)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

            elif data == "filter":
                text, kb = _filter_keyboard()
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

            elif data.startswith("ft:"):
                course_id = int(data.split(":")[1])
                excluded = db.get_excluded_course_ids(conn)
                was_excluded = course_id in excluded
                if was_excluded:
                    excluded.remove(course_id)
                else:
                    excluded.append(course_id)
                db.set_excluded_course_ids(conn, excluded)

                # Re-render filter menu
                text, kb = _filter_keyboard()
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

                # If re-enabled, trigger a catch-up sync in the background
                if was_excluded:
                    sync_fn = context.bot_data.get("sync_callback")
                    if sync_fn:
                        asyncio.create_task(sync_fn())

            elif data == "filter_done":
                text, kb = _courses_keyboard()
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

            elif data.startswith("cd:"):
                course_id = int(data.split(":")[1])
                text, kb = _course_detail_text(course_id)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

            elif data.startswith("cdp:"):
                parts = data.split(":")
                course_id = int(parts[1])
                page = int(parts[2])
                text, kb = _course_detail_text(course_id, page)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

            elif data == "freq":
                text, kb = _freq_keyboard(scheduler.interval_minutes)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

            elif data.startswith("fs:"):
                minutes = int(data.split(":")[1])
                scheduler.reschedule(minutes)
                db.set_preference(conn, "sync_interval_minutes", str(minutes))
                text = f"Sync interval updated to <b>every {_format_interval(minutes)}</b>"
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=_back_home_keyboard())

            elif data == "do_sync":
                await query.edit_message_text("Starting sync...")
                try:
                    result = await sync_callback()
                    await query.edit_message_text(
                        _format_sync_result(result), reply_markup=_back_home_keyboard(),
                    )
                except Exception as e:
                    logger.error("Sync via callback failed: %s", e)
                    await query.edit_message_text(f"Sync failed: {e}", reply_markup=_back_home_keyboard())

            elif data == "status":
                last_run = status_callback()
                if last_run is None:
                    text = "No sync has been run yet."
                else:
                    error_count = len(last_run.get("errors", []))
                    text = (
                        f"Last sync: {last_run['started_at']}\n"
                        f"Status: {last_run['status']}\n"
                        f"Courses: {last_run['courses_synced']}\n"
                        f"Files uploaded: {last_run['files_uploaded']}\n"
                        f"Files updated: {last_run['files_updated']}\n"
                        f"Notifications: {last_run['notifications']}\n"
                        f"Errors: {error_count}"
                    )
                await query.edit_message_text(text, reply_markup=_back_home_keyboard())

            elif data == "outstanding":
                await query.edit_message_text("Checking submissions...")
                all_courses = db.get_all_courses(conn)
                excluded_ids = set(db.get_excluded_course_ids(conn))
                active = [c for c in all_courses if c["course_id"] not in excluded_ids]
                text = await _build_outstanding_text(active, canvas, conn)
                try:
                    await query.edit_message_text(
                        text, parse_mode="HTML", reply_markup=_back_home_keyboard(),
                    )
                except BadRequest:
                    await query.edit_message_text(text, reply_markup=_back_home_keyboard())

        except BadRequest as e:
            if "Message is not modified" in str(e):
                pass  # User pressed the same button twice — ignore
            else:
                logger.error("Callback handler error: %s", e)

    # ── register handlers ─────────────────────────────────────────────

    app.add_handler(CommandHandler("start", cmd_start, filters=chat_filter))
    app.add_handler(CommandHandler("sync", cmd_sync, filters=chat_filter))
    app.add_handler(CommandHandler("status", cmd_status, filters=chat_filter))
    app.add_handler(CommandHandler("courses", cmd_courses, filters=chat_filter))
    app.add_handler(CommandHandler("frequency", cmd_frequency, filters=chat_filter))
    app.add_handler(CommandHandler("outstanding", cmd_outstanding, filters=chat_filter))
    app.add_handler(CallbackQueryHandler(handle_callback))

    return app
