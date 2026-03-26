"""Telegram /prep ConversationHandler for multi-step study pack generation."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import timedelta

from dateutil import parser as dateutil_parser

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from canvas_companion import db
from canvas_companion.calendar_service import CalendarService
from canvas_companion.gemini_service import GeminiService
from canvas_companion.models import PrepRequest, PrepType
from canvas_companion.prep_agent import generate_study_pack

logger = logging.getLogger(__name__)

SELECTING_COURSE = 0
SELECTING_PREP_TYPE = 1
ENTERING_QUIZ_NAME = 2
ENTERING_FILE_NAME = 3
AWAITING_APPROVAL = 4
ENTERING_DATETIME = 5

_MAX_FILE_ATTEMPTS = 3


def create_prep_conversation(
    chat_filter: filters.BaseFilter,
    conn: sqlite3.Connection,
    gemini: GeminiService | None,
    calendar: CalendarService | None,
) -> ConversationHandler:
    """Build the ConversationHandler for /prep."""

    async def cmd_prep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Entry point: show course selection keyboard (from /prep command or button)."""
        if gemini is None:
            text = (
                "The /prep feature requires Gemini API configuration.\n"
                "Set CC_GEMINI_API_KEY in your .env file."
            )
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(text)
            else:
                await update.message.reply_text(text)  # type: ignore[union-attr]
            return ConversationHandler.END

        if update.callback_query:
            await update.callback_query.answer()

        courses = db.get_all_courses(conn)
        excluded = set(db.get_excluded_course_ids(conn))
        active = [c for c in courses if c["course_id"] not in excluded]

        if not active:
            text = "No courses found. Run /sync first."
            if update.callback_query:
                await update.callback_query.edit_message_text(text)
            else:
                await update.message.reply_text(text)  # type: ignore[union-attr]
            return ConversationHandler.END

        buttons: list[list[InlineKeyboardButton]] = []
        for c in active:
            label = c["course_code"] or c["name"]
            buttons.append([
                InlineKeyboardButton(label, callback_data=f"prep_c:{c['course_id']}"),
            ])
        buttons.append([InlineKeyboardButton("Cancel", callback_data="prep_cancel")])

        markup = InlineKeyboardMarkup(buttons)
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "<b>Study Prep</b>\n\nWhich module?",
                parse_mode="HTML",
                reply_markup=markup,
            )
        else:
            await update.message.reply_text(  # type: ignore[union-attr]
                "<b>Study Prep</b>\n\nWhich module?",
                parse_mode="HTML",
                reply_markup=markup,
            )
        return SELECTING_COURSE

    async def select_course(
        update: Update, context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        """User picked a course; show prep type options."""
        query = update.callback_query
        await query.answer()  # type: ignore[union-attr]
        data = query.data or ""  # type: ignore[union-attr]

        if data == "prep_cancel":
            await query.edit_message_text("Prep cancelled.")  # type: ignore[union-attr]
            return ConversationHandler.END

        course_id = int(data.split(":")[1])
        course = db.get_course(conn, course_id)
        course_name = course["name"] if course else f"Course {course_id}"
        course_code = (course["course_code"] or course_name) if course else course_name

        context.user_data["prep_course_id"] = course_id  # type: ignore[index]
        context.user_data["prep_course_name"] = course_name  # type: ignore[index]
        context.user_data["prep_course_code"] = course_code  # type: ignore[index]
        context.user_data["file_attempts"] = 0  # type: ignore[index]

        buttons = [
            [InlineKeyboardButton("Material Summary", callback_data="prep_t:material_summary")],
            [InlineKeyboardButton("Quiz Prep", callback_data="prep_t:quiz_prep")],
            [InlineKeyboardButton("Cancel", callback_data="prep_cancel")],
        ]

        await query.edit_message_text(  # type: ignore[union-attr]
            f"<b>{course_name}</b>\n\nHow can I assist you?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return SELECTING_PREP_TYPE

    async def select_prep_type(
        update: Update, context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        """User picked prep type; route to appropriate next step."""
        query = update.callback_query
        await query.answer()  # type: ignore[union-attr]
        data = query.data or ""  # type: ignore[union-attr]

        if data == "prep_cancel":
            await query.edit_message_text("Prep cancelled.")  # type: ignore[union-attr]
            return ConversationHandler.END

        prep_type = data.split(":")[1]
        context.user_data["prep_type"] = prep_type  # type: ignore[index]

        course_name = context.user_data["prep_course_name"]  # type: ignore[index]

        if prep_type == "quiz_prep":
            await query.edit_message_text(  # type: ignore[union-attr]
                f"<b>{course_name}</b> | Quiz Prep\n\n"
                "What is the name of the quiz?\n"
                "<i>e.g. \"Quiz 3\" or \"Chapter 5 Quiz\"</i>",
                parse_mode="HTML",
            )
            return ENTERING_QUIZ_NAME
        else:
            await query.edit_message_text(  # type: ignore[union-attr]
                f"<b>{course_name}</b> | Material Summary\n\n"
                "What's the file name of the material in Google Drive?\n"
                "<i>Type the file name or part of it, e.g. \"Lecture 3\" or \"Chapter 5.pdf\"</i>",
                parse_mode="HTML",
            )
            return ENTERING_FILE_NAME

    async def enter_quiz_name(
        update: Update, context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        """User typed quiz name; ask for material file."""
        quiz_name = update.message.text.strip()  # type: ignore[union-attr]
        context.user_data["prep_quiz_name"] = quiz_name  # type: ignore[index]

        course_name = context.user_data["prep_course_name"]  # type: ignore[index]
        await update.message.reply_text(  # type: ignore[union-attr]
            f"<b>{course_name}</b> | Quiz Prep — {quiz_name}\n\n"
            "Which material is this quiz based on?\n"
            "<i>Type the file name or part of it from Google Drive, "
            "e.g. \"Lecture 5\" or \"Chapter 5.pdf\"</i>",
            parse_mode="HTML",
        )
        return ENTERING_FILE_NAME

    async def enter_file_name(
        update: Update, context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        """User typed a file name; look it up and generate the study pack."""
        filename_query = update.message.text.strip()  # type: ignore[union-attr]
        course_id = context.user_data["prep_course_id"]  # type: ignore[index]
        course_name = context.user_data["prep_course_name"]  # type: ignore[index]
        course_code = context.user_data["prep_course_code"]  # type: ignore[index]
        prep_type = context.user_data["prep_type"]  # type: ignore[index]
        attempts = context.user_data.get("file_attempts", 0)  # type: ignore[index]

        chunks, canonical_name = db.get_chunks_for_file(conn, course_id, filename_query)

        if canonical_name is None:
            attempts += 1
            context.user_data["file_attempts"] = attempts  # type: ignore[index]

            if attempts >= _MAX_FILE_ATTEMPTS:
                await update.message.reply_text(  # type: ignore[union-attr]
                    "Too many failed attempts. Use /cancel to exit, "
                    "or run /sync to update your files first.",
                )
                return ConversationHandler.END

            # Show suggestions
            suggestions = db.search_files_by_name(conn, course_id, filename_query)
            if suggestions:
                names = "\n".join(f"  • {s['display_name']}" for s in suggestions)
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"Couldn't find a file matching <i>{filename_query}</i>. "
                    f"Did you mean one of these?\n\n{names}\n\n"
                    "Please type the file name again, or /cancel to exit.",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"No file found matching <i>{filename_query}</i> in {course_name}.\n\n"
                    "Make sure the file has been synced. "
                    "Type the file name again, or /cancel to exit.",
                    parse_mode="HTML",
                )
            return ENTERING_FILE_NAME

        context.user_data["prep_file_name"] = canonical_name  # type: ignore[index]

        # Send generating message
        msg = await update.message.reply_text(  # type: ignore[union-attr]
            "Generating... This may take a moment.",
        )

        quiz_name = context.user_data.get("prep_quiz_name")  # type: ignore[index]
        request = PrepRequest(
            course_id=course_id,
            course_name=course_name,
            course_code=course_code,
            prep_type=PrepType(prep_type),
            file_display_name=canonical_name,
            quiz_name=quiz_name,
        )

        try:
            study_pack = await generate_study_pack(request, chunks, gemini)  # type: ignore[arg-type]
        except Exception as e:
            logger.error("Study pack generation failed: %s", e)
            await msg.edit_text(f"Generation failed: {e}")
            return ConversationHandler.END

        context.user_data["prep_study_pack"] = study_pack  # type: ignore[index]

        # Truncate if needed for Telegram's 4096 char limit
        if len(study_pack) > 3800:
            display_pack = study_pack[:3800] + "\n\n<i>(...truncated)</i>"
        else:
            display_pack = study_pack

        # Build approval buttons
        if calendar is not None:
            if prep_type == "quiz_prep":
                cal_label = "Add quiz to calendar"
            else:
                cal_label = "Add study session to calendar"
            buttons: list[list[InlineKeyboardButton]] = [[
                InlineKeyboardButton(cal_label, callback_data="prep_add_cal"),
                InlineKeyboardButton("Skip", callback_data="prep_skip"),
            ]]
        else:
            buttons = [[InlineKeyboardButton("Done", callback_data="prep_skip")]]

        try:
            await msg.edit_text(
                display_pack,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception:
            await msg.edit_text(
                study_pack[:3800],
                reply_markup=InlineKeyboardMarkup(buttons),
            )

        return AWAITING_APPROVAL

    async def handle_approval(
        update: Update, context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        """User clicked Add to Calendar or Skip."""
        query = update.callback_query
        await query.answer()  # type: ignore[union-attr]
        data = query.data or ""  # type: ignore[union-attr]

        if data == "prep_add_cal":
            prep_type = context.user_data.get("prep_type", "")  # type: ignore[index]
            if prep_type == "quiz_prep":
                prompt_text = (
                    "When is the quiz? Include date, time, and optionally duration.\n"
                    "<i>e.g. \"28 Mar 2026 2pm, 1 hour\" or \"28 Mar 2026 14:00-16:00\"</i>\n"
                    "(Default: 2 hours if not specified)"
                )
            else:
                prompt_text = (
                    "When would you like to study? Include date, time, and optionally duration.\n"
                    "<i>e.g. \"tomorrow 3pm, 1.5 hours\" or \"28 Mar 2026 14:00-16:00\"</i>\n"
                    "(Default: 2 hours if not specified)"
                )
            await query.message.reply_text(prompt_text, parse_mode="HTML")  # type: ignore[union-attr]
            return ENTERING_DATETIME

        # Skip — record session and end
        _record_session(context, event_datetime=None, calendar_event_id=None)
        await query.edit_message_text(  # type: ignore[union-attr]
            (query.message.text_html or query.message.text)  # type: ignore[union-attr]
            + "\n\nDone! Good luck with your studies.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    def _parse_event_datetime(raw: str):
        """Parse user input into (start_dt, end_dt).

        Supports:
          - "28 Mar 2026 14:00-16:00"  → time range
          - "tomorrow 3pm, 1 hour"      → datetime + duration
          - "tomorrow 3pm"              → datetime only (default 2h)
        """
        # Pattern 1: HH:MM-HH:MM time range at end of string
        range_match = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$', raw)
        if range_match:
            prefix = raw[:range_match.start()].strip()
            start_dt = dateutil_parser.parse(f"{prefix} {range_match.group(1)}", fuzzy=True)
            end_dt = dateutil_parser.parse(f"{prefix} {range_match.group(2)}", fuzzy=True)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            return start_dt, end_dt

        # Pattern 2: "datetime, duration" (e.g. "tomorrow 3pm, 1.5 hours")
        comma_match = re.search(r',\s*(.+)$', raw)
        if comma_match:
            dur_str = comma_match.group(1).strip()
            dur_match = re.match(
                r'(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\b',
                dur_str, re.IGNORECASE,
            )
            if dur_match:
                amount = float(dur_match.group(1))
                unit = dur_match.group(2).lower()
                delta = timedelta(hours=amount) if unit[0] == 'h' else timedelta(minutes=amount)
                start_dt = dateutil_parser.parse(raw[:comma_match.start()].strip(), fuzzy=True)
                return start_dt, start_dt + delta

        # Pattern 3: datetime only — default 2 hours
        start_dt = dateutil_parser.parse(raw, fuzzy=True)
        return start_dt, start_dt + timedelta(hours=2)

    async def enter_datetime(
        update: Update, context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        """User typed date/time; create calendar event."""
        raw = update.message.text.strip()  # type: ignore[union-attr]

        try:
            event_dt, end_dt = _parse_event_datetime(raw)
        except (ValueError, OverflowError):
            await update.message.reply_text(  # type: ignore[union-attr]
                'Could not parse that date. Please try again '
                '(e.g. "28 Mar 2026 2pm, 1 hour" or "28 Mar 2026 14:00-16:00").',
            )
            return ENTERING_DATETIME

        course_name = context.user_data.get("prep_course_name", "")  # type: ignore[index]
        course_code = context.user_data.get("prep_course_code", "")  # type: ignore[index]
        prep_type = context.user_data.get("prep_type", "")  # type: ignore[index]
        file_name = context.user_data.get("prep_file_name", "")  # type: ignore[index]
        quiz_name = context.user_data.get("prep_quiz_name", "")  # type: ignore[index]
        study_pack = context.user_data.get("prep_study_pack", "")  # type: ignore[index]

        if prep_type == "quiz_prep":
            event_title = f"{course_code} {quiz_name}"
        else:
            event_title = f"{course_code} {file_name} Study Session"

        if calendar is not None:
            try:
                event = calendar.create_event(
                    summary=event_title,
                    description=study_pack[:5000],
                    start_time=event_dt,
                    end_time=end_dt,
                )
                event_link = event.get("htmlLink", "")
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"Calendar event created!\n{event_link}",
                )
                _record_session(context, event_dt.isoformat(), event.get("id"))
            except Exception as e:
                logger.error("Calendar event creation failed: %s", e)
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"Failed to create calendar event: {e}\n\nDone! Good luck with your studies.",
                )
                _record_session(context, event_dt.isoformat(), None)
        else:
            _record_session(context, event_dt.isoformat(), None)
            await update.message.reply_text("Done! Good luck with your studies.")  # type: ignore[union-attr]

        return ConversationHandler.END

    def _record_session(
        context: ContextTypes.DEFAULT_TYPE,
        event_datetime: str | None,
        calendar_event_id: str | None,
    ) -> None:
        prep_type = context.user_data.get("prep_type", "")  # type: ignore[index]
        file_name = context.user_data.get("prep_file_name", "")  # type: ignore[index]
        quiz_name = context.user_data.get("prep_quiz_name")  # type: ignore[index]
        scope = f"{quiz_name} | {file_name}" if quiz_name else file_name
        db.record_prep_session(
            conn,
            context.user_data["prep_course_id"],  # type: ignore[index]
            prep_type,
            scope,
            event_datetime,
            context.user_data.get("prep_study_pack"),  # type: ignore[index]
            calendar_event_id,
        )

    async def cancel(
        update: Update, context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        """Handle /cancel during conversation."""
        await update.message.reply_text("Prep cancelled.")  # type: ignore[union-attr]
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[
            CommandHandler("prep", cmd_prep, filters=chat_filter),
            CallbackQueryHandler(cmd_prep, pattern=r"^prep_start$"),
        ],
        states={
            SELECTING_COURSE: [
                CallbackQueryHandler(
                    select_course, pattern=r"^prep_c:\d+$|^prep_cancel$",
                ),
            ],
            SELECTING_PREP_TYPE: [
                CallbackQueryHandler(
                    select_prep_type, pattern=r"^prep_t:\w+$|^prep_cancel$",
                ),
            ],
            ENTERING_QUIZ_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_quiz_name),
            ],
            ENTERING_FILE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_file_name),
            ],
            AWAITING_APPROVAL: [
                CallbackQueryHandler(
                    handle_approval, pattern=r"^prep_add_cal$|^prep_skip$",
                ),
            ],
            ENTERING_DATETIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_datetime),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=600,
    )
