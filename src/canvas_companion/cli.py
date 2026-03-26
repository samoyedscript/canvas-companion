"""Typer CLI: sync, run, doctor subcommands."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import typer

app = typer.Typer(
    name="canvas-companion",
    help="Canvas LMS monitor with Drive sync and Telegram alerts",
)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Suppress httpx request logs — they expose the Telegram bot token in URLs
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _load_settings():
    from canvas_companion.config import Settings

    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as e:
        typer.echo(f"Configuration error: {e}", err=True)
        typer.echo("Run 'canvas-companion doctor' to diagnose.", err=True)
        raise typer.Exit(code=1)


def _build_components(settings):
    from canvas_companion.canvas_api import CanvasClient
    from canvas_companion.db import get_connection, init_schema
    from canvas_companion.drive_sync import DriveSync
    from canvas_companion.telegram_notifier import TelegramNotifier

    conn = get_connection(settings.db_path)
    init_schema(conn)

    canvas = CanvasClient(
        base_url=settings.canvas_base_url,
        api_token=settings.canvas_api_token.get_secret_value(),
    )
    drive = DriveSync(
        credentials_path=settings.google_credentials_path,
        token_path=settings.google_token_path,
        root_folder_name=settings.drive_root_folder_name,
    )
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
    )

    gemini = None
    if settings.gemini_api_key:
        from canvas_companion.gemini_service import GeminiService

        gemini = GeminiService(
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
        )

    calendar = None
    try:
        from canvas_companion.calendar_service import CalendarService

        calendar = CalendarService(drive.credentials)
    except Exception as e:
        logging.getLogger(__name__).warning("Calendar service unavailable: %s", e)

    return conn, canvas, drive, notifier, gemini, calendar


@app.command()
def sync() -> None:
    """Run a single sync cycle and exit.

    This is the recommended first command to run after setup. It performs an
    initial sync of all courses, files, assignments, and announcements from
    Canvas, uploads files to Google Drive, and sends Telegram notifications.
    Use this to verify your configuration before starting the long-running daemon.
    """
    settings = _load_settings()
    _setup_logging(settings.log_level)

    from canvas_companion.sync_engine import run_sync

    conn, canvas, drive, notifier, _gemini, _calendar = _build_components(settings)

    async def _run():
        try:
            result = await run_sync(canvas, drive, notifier, conn)
            return result
        finally:
            await canvas.close()

    result = asyncio.run(_run())

    typer.echo(f"\nSync completed at {result.finished_at.isoformat()}")
    typer.echo(f"  Courses synced:      {result.courses_synced}")
    typer.echo(f"  Files uploaded:      {result.files_uploaded}")
    typer.echo(f"  Files updated:       {result.files_updated}")
    typer.echo(f"  Notifications sent:  {result.notifications_sent}")
    if result.errors:
        typer.echo(f"  Errors: {len(result.errors)}")
        for err in result.errors:
            typer.echo(f"    - {err}", err=True)
        raise typer.Exit(code=1)


@app.command()
def run() -> None:
    """Start long-running daemon: scheduled sync + Telegram bot."""
    settings = _load_settings()
    _setup_logging(settings.log_level)

    from canvas_companion import db as db_mod
    from canvas_companion.db import get_last_sync_run
    from canvas_companion.scheduler import SyncScheduler
    from canvas_companion.sync_engine import run_sync
    from canvas_companion.telegram_bot import create_bot_application

    conn, canvas, drive, notifier, gemini, calendar = _build_components(settings)

    async def do_sync():
        return await run_sync(canvas, drive, notifier, conn)

    def get_status():
        return get_last_sync_run(conn)

    # Use persisted interval if the user changed it via /frequency, else config default
    saved_interval = db_mod.get_preference(conn, "sync_interval_minutes")
    interval = int(saved_interval) if saved_interval else settings.sync_interval_minutes
    scheduler = SyncScheduler(interval, do_sync)

    bot_app = create_bot_application(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
        sync_callback=do_sync,
        status_callback=get_status,
        conn=conn,
        canvas=canvas,
        scheduler=scheduler,
        gemini=gemini,
        calendar=calendar,
    )

    async def _main():
        # Run initial sync
        typer.echo("Running initial sync...")
        result = await do_sync()
        typer.echo(f"Initial sync done: {result.courses_synced} courses, "
                   f"{result.files_uploaded} files uploaded, "
                   f"{result.notifications_sent} notifications sent")

        # Start scheduler
        scheduler.start()
        typer.echo(f"Scheduler started (every {interval} min)")

        # Start bot polling
        typer.echo("Starting Telegram bot...")
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling()  # type: ignore[union-attr]

        # Wait for shutdown signal
        stop_event = asyncio.Event()

        def _signal_handler():
            typer.echo("\nShutting down...")
            stop_event.set()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

        await stop_event.wait()

        # Cleanup
        await bot_app.updater.stop()  # type: ignore[union-attr]
        await bot_app.stop()
        await bot_app.shutdown()
        scheduler.shutdown()
        await canvas.close()
        conn.close()

    asyncio.run(_main())


@app.command()
def doctor() -> None:
    """Check configuration, credentials, and connectivity."""
    typer.echo("Canvas Companion — Doctor\n")

    # 1. Config
    typer.echo("[1/6] Configuration...")
    try:
        settings = _load_settings()
        typer.echo("  PASS: All required settings loaded")
    except SystemExit:
        return

    _setup_logging("WARNING")

    # 2. Canvas API
    typer.echo("[2/6] Canvas API...")
    import httpx

    try:
        resp = httpx.get(
            f"{settings.canvas_base_url}/api/v1/users/self",
            headers={"Authorization": f"Bearer {settings.canvas_api_token.get_secret_value()}"},
            timeout=10,
        )
        resp.raise_for_status()
        user = resp.json()
        typer.echo(f"  PASS: Authenticated as {user.get('name', 'unknown')}")
    except Exception as e:
        typer.echo(f"  FAIL: {e}", err=True)

    # 3. Google Drive
    typer.echo("[3/6] Google Drive...")
    drive = None
    try:
        from canvas_companion.drive_sync import DriveSync

        drive = DriveSync(
            credentials_path=settings.google_credentials_path,
            token_path=settings.google_token_path,
            root_folder_name=settings.drive_root_folder_name,
        )
        folder_id = drive.ensure_root_folder()
        typer.echo(f"  PASS: Root folder ready (id={folder_id})")
    except Exception as e:
        typer.echo(f"  FAIL: {e}", err=True)

    # 4. Telegram
    typer.echo("[4/6] Telegram...")
    import asyncio

    from telegram import Bot

    async def _check_telegram():
        bot = Bot(token=settings.telegram_bot_token.get_secret_value())
        me = await bot.get_me()
        return me

    try:
        me = asyncio.run(_check_telegram())
        typer.echo(f"  PASS: Bot @{me.username} is reachable")
    except Exception as e:
        typer.echo(f"  FAIL: {e}", err=True)

    # 5. Gemini API
    typer.echo("[5/6] Gemini API...")
    if settings.gemini_api_key:
        try:
            from canvas_companion.gemini_service import GeminiService

            gemini = GeminiService(
                api_key=settings.gemini_api_key.get_secret_value(),
                model=settings.gemini_model,
            )
            ok = asyncio.run(gemini.check_connectivity())
            if ok:
                typer.echo(f"  PASS: Gemini ({settings.gemini_model}) is reachable")
            else:
                typer.echo("  FAIL: Gemini returned unexpected response", err=True)
        except Exception as e:
            typer.echo(f"  FAIL: {e}", err=True)
    else:
        typer.echo("  SKIP: CC_GEMINI_API_KEY not set (optional, needed for /prep)")

    # 6. Google Calendar
    typer.echo("[6/6] Google Calendar...")
    if drive is not None:
        try:
            from canvas_companion.calendar_service import CalendarService

            cal = CalendarService(drive.credentials)
            if cal.check_connectivity():
                typer.echo("  PASS: Calendar API is accessible")
            else:
                typer.echo("  FAIL: Calendar API returned error", err=True)
        except Exception as e:
            typer.echo(f"  FAIL: {e}", err=True)
            typer.echo(
                "  HINT: Enable the Google Calendar API and add calendar.events scope.\n"
                "  Then delete credentials/token.json and re-run doctor to re-authorize.",
                err=True,
            )
    else:
        typer.echo("  SKIP: Google Drive not configured (Calendar requires Drive OAuth)")

    typer.echo("\nDone.")
