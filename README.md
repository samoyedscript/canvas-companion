# Canvas Companion

A monitoring and automation tool for Canvas LMS that syncs course files to Google Drive and sends real-time notifications via Telegram. Built for NUS students.

## Features

- **Continuous Canvas Monitoring** — Automatically detects new assignments, announcements, and files across all enrolled courses.
- **Google Drive Sync** — Uploads and updates course files to Google Drive, organised into per-course folders.
- **Telegram Notifications** — Sends alerts for new assignments, due date changes, new announcements, and synced files.
- **Deadline Reminders** — Escalating urgency levels (Normal, Upcoming, Urgent, Critical) as deadlines approach.
- **Interactive Telegram Bot** — Browse courses, check outstanding assignments, trigger manual syncs, and adjust settings directly from Telegram.
- **AI Study Pack Generation** — `/prep` uses Google Gemini to generate summaries and quiz prep from your course materials, with a critique pass for quality.
- **Google Calendar Integration** — Add study sessions or quiz schedules to Google Calendar directly from the bot.
- **PDF Full-Text Search** — Course PDFs are indexed and searchable when generating study packs.
- **Course Filtering** — Exclude courses you don't want to track.
- **Configurable Sync Interval** — Set the sync frequency from 5 minutes to 1 week, adjustable at runtime via the bot.
- **Academic Calendar** — Displays the current NUS semester week in the bot.
- **Diagnostics** — Built-in `doctor` command to verify all credentials and connectivity.

## Prerequisites

- Python 3.12 or higher
- A Canvas LMS account with API access
- A Google Cloud project with the Google Drive API enabled
- A Telegram account

## Setup Guide

See [SETUP.md](SETUP.md) for the full setup guide, including how to configure Canvas API, Google Drive, Telegram, and environment variables.

## Usage

### One-Time Sync

Run a single sync cycle to test your setup:

```bash
canvas-companion sync
```

### Start the Daemon

Run the long-lived process with scheduled syncing and the Telegram bot:

```bash
canvas-companion run
```

This will:
1. Perform an initial sync of all courses.
2. Start the scheduler for periodic syncs.
3. Start the Telegram bot for interactive commands.
4. Run until stopped with `Ctrl+C`.

### Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Home screen with current academic week |
| `/sync` | Trigger a manual sync |
| `/status` | View results from the last sync |
| `/courses` | Browse and filter enrolled courses |
| `/outstanding` | Check unsubmitted assignments with urgency indicators |
| `/frequency` | Change the sync interval |
| `/prep` | Generate an AI-powered study pack from course materials |

### Study Pack Generation (`/prep`)

The `/prep` command walks you through a multi-step conversation to generate a study pack:

1. Select a course.
2. Choose **Material Summary** or **Quiz Prep**.
3. Enter the name of the course file to base the pack on.
4. Review the generated study pack.
5. Optionally add a calendar event.

**Scheduling a calendar event:**

When prompted for a date and time, you can include a duration:

```
28 Mar 2026 2pm, 1 hour
28 Mar 2026 14:00-16:00
tomorrow 3pm
```

If no duration is given, the event defaults to 2 hours.

> Requires `CC_GEMINI_API_KEY` in your `.env`. See [SETUP.md](SETUP.md) for configuration.

## Academic Calendar

The bot displays the current NUS academic week on the `/start` screen. The calendar data is hard-coded in `src/canvas_companion/nus_calendar.py` for **AY2025-2026**, based on the [official NUS Registrar calendar](https://nus.edu.sg/registrar/docs/default-source/calendar/ay2025-2026.pdf).

**When a new academic year begins**, you will need to update this file:

1. Download the new academic calendar PDF from the NUS Registrar.
2. Open `src/canvas_companion/nus_calendar.py`.
3. Update the `AY_2025_2026` dictionary:
   - Rename it to match the new AY (e.g. `AY_2026_2027`).
   - Update the `"ay_name"` string.
   - Replace all the semester period dates with the new dates from the PDF.
4. Update the reference to the dictionary name in `get_current_period()` if you renamed it.

If you are not an NUS student, you can adapt this file entirely to your own institution's academic calendar by replacing the semester and period entries with your own dates.

## Running Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=canvas_companion
```

## License

This project is provided as-is for personal and educational use.
