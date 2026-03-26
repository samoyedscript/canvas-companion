# Setup Guide

## 1. Clone and Install

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

## 2. Canvas API Token

1. Log in to your Canvas LMS instance (e.g. `https://canvas.nus.edu.sg`).
2. Go to **Account** > **Settings**.
3. Scroll down to **Approved Integrations** and click **+ New Access Token**.
4. Give it a description (e.g. "Canvas Companion") and optionally set an expiry date.
5. Click **Generate Token**.
6. Copy the token immediately — it will not be shown again.

## 3. Google Cloud Console Setup

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

## 4. Telegram Bot Setup

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts:
   - Choose a display name (e.g. "Canvas Companion").
   - Choose a username ending in `bot` (e.g. `my_canvas_companion_bot`).
3. BotFather will reply with a **bot token**. Copy it somewhere safe and do not commit it.

**Getting your Chat ID:**

1. Send any message to your new bot on Telegram.
2. Open this URL in your browser (replace `<BOT_TOKEN>` with your token):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
3. Find the `"chat":{"id": ...}` field in the JSON response. This number is your chat ID.

## 5. Environment Variables

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
CC_TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here # Token from step 4
CC_TELEGRAM_CHAT_ID=123456789                     # Chat ID from step 4

# Scheduler
CC_SYNC_INTERVAL_MINUTES=30                       # Sync every 30 minutes

# Database
CC_DB_PATH=canvas_companion.db

# Logging
CC_LOG_LEVEL=INFO

# Gemini API (optional, required for /prep)
CC_GEMINI_API_KEY=your_gemini_api_key_here
CC_GEMINI_MODEL=gemini-2.5-flash
```

## 6. Gemini API Setup (for /prep)

The `/prep` study pack feature uses Google's Gemini API for AI-powered study material generation.

1. Go to [Google AI Studio](https://aistudio.google.com/apikey).
2. Click **Create API Key**.
3. Select your existing Google Cloud project (the same one used for Drive).
4. Copy the API key.
5. Add to your `.env` file:

```env
CC_GEMINI_API_KEY=your_key_here
CC_GEMINI_MODEL=gemini-2.5-flash
```

The default model `gemini-2.5-flash` offers a good balance of speed and quality. You can also use `gemini-2.5-pro` for higher quality at the cost of slower generation.

## 7. Google Calendar API Setup (for /prep)

The `/prep` feature can optionally create Google Calendar events for your study sessions.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Select your existing project (the same one used for Drive).
3. Navigate to **APIs & Services** > **Library**.
4. Search for **Google Calendar API** and click **Enable**.
5. Go to **APIs & Services** > **OAuth consent screen**.
   - Click **Edit App**.
   - On the **Scopes** step, add: `https://www.googleapis.com/auth/calendar.events`
   - Save changes.
6. **Re-authorize the app**: Delete `credentials/token.json` and run `canvas-companion doctor`.
   A browser window will open for you to re-authorize with the new Calendar scope.

```bash
rm credentials/token.json
canvas-companion doctor
```

> **Note:** If you skip this step, the `/prep` feature will still work for generating study packs,
> but the "Add to Calendar" button will not appear.

## 8. Verify Setup

Run the built-in diagnostic tool to check that everything is configured correctly:

```bash
canvas-companion doctor
```

This will test your configuration, Canvas API connection, Google Drive credentials, Telegram bot connectivity, Gemini API access, and Google Calendar connectivity.
