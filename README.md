# Canvas Companion

A monitoring and automation tool for Canvas LMS that syncs course files to Google Drive and sends real-time notifications via Telegram. Built for NUS students.

## Features

- **Continuous Canvas Monitoring** — Automatically detects new assignments, announcements, and files across all enrolled courses.
- **Google Drive Sync** — Uploads and updates course files to Google Drive, organised into per-course folders.
- **Telegram Notifications** — Sends alerts for new assignments, due date changes, new announcements, and synced files.
- **Deadline Reminders** — Escalating urgency levels (Normal, Upcoming, Urgent, Critical) as deadlines approach.
- **Interactive Telegram Bot** — Browse courses, check outstanding assignments, trigger manual syncs, and adjust settings directly from Telegram.
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

### 1. Clone and Install

```bash
git clone https://github.com/<your-username>/canvas-companion.git
cd canvas-companion
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the package:

```bash
pip install -e .
```

For development (includes testing and linting tools):

```bash
pip install -e ".[dev]"
```

### 2. Canvas API Token

1. Log in to your Canvas LMS instance (e.g. `https://canvas.nus.edu.sg`).
2. Go to **Account** > **Settings**.
3. Scroll down to **Approved Integrations** and click **+ New Access Token**.
4. Give it a description (e.g. "Canvas Companion") and optionally set an expiry date.
5. Click **Generate Token**.
6. Copy the token immediately — it will not be shown again.

### 3. Google Cloud Console Setup

You need OAuth 2.0 credentials so Canvas Companion can upload files to your Google Drive.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Navigate to **APIs & Services** > **Library**.
4. Search for **Google Drive API** and click **Enable**.
5. Go to **APIs & Services** > **OAuth consent screen**.
   - Choose **External** as the user type.
   - Fill in the required fields (app name, user support email, developer contact email).
   - On the **Scopes** step, add the scope: `https://www.googleapis.com/auth/drive.file`.
   - On the **Test users** step, add your own Google account email.
   - Complete the wizard.
6. Go to **APIs & Services** > **Credentials**.
   - Click **+ Create Credentials** > **OAuth client ID**.
   - Select **Desktop app** as the application type.
   - Give it a name and click **Create**.
7. Click the download icon next to the newly created credential to download the JSON file.
8. Save it as `credentials/credentials.json` inside the project directory:

```bash
mkdir -p credentials
mv ~/Downloads/client_secret_*.json credentials/credentials.json
```

On first run, a browser window will open for you to authorise the app with your Google account. The resulting token is saved to `credentials/token.json` and refreshed automatically.

### 4. Telegram Bot Setup

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts:
   - Choose a display name (e.g. "Canvas Companion").
   - Choose a username ending in `bot` (e.g. `my_canvas_companion_bot`).
3. BotFather will reply with a **bot token** in the format `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`. Copy this token.

**Getting your Chat ID:**

1. Send any message to your new bot on Telegram.
2. Open this URL in your browser (replace `<BOT_TOKEN>` with your token):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
3. Find the `"chat":{"id": ...}` field in the JSON response. This number is your chat ID.

### 5. Environment Variables

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Canvas LMS
CC_CANVAS_BASE_URL=https://canvas.nus.edu.sg    # Your Canvas instance URL
CC_CANVAS_API_TOKEN=your_canvas_token_here       # Token from step 2

# Google Drive OAuth
CC_GOOGLE_CREDENTIALS_PATH=credentials/credentials.json
CC_GOOGLE_TOKEN_PATH=credentials/token.json
CC_DRIVE_ROOT_FOLDER_NAME=Canvas Companion       # Name of the root folder in your Drive

# Telegram
CC_TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234...      # Token from step 4
CC_TELEGRAM_CHAT_ID=123456789                     # Chat ID from step 4

# Scheduler
CC_SYNC_INTERVAL_MINUTES=30                       # Sync every 30 minutes

# Database
CC_DB_PATH=canvas_companion.db

# Logging
CC_LOG_LEVEL=INFO
```

### 6. Verify Setup

Run the built-in diagnostic tool to check that everything is configured correctly:

```bash
canvas-companion doctor
```

This will test your configuration, Canvas API connection, Google Drive credentials, and Telegram bot connectivity.

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
