"""APScheduler wrapper for periodic sync runs."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_JOB_ID = "canvas_sync"


class SyncScheduler:
    def __init__(
        self,
        interval_minutes: int,
        sync_fn: Callable[[], Coroutine[Any, Any, Any]],
    ) -> None:
        self._scheduler = AsyncIOScheduler()
        self._sync_fn = sync_fn
        self._interval = interval_minutes

    def start(self) -> None:
        self._scheduler.add_job(
            self._sync_fn,
            "interval",
            minutes=self._interval,
            id=_JOB_ID,
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("Scheduler started: syncing every %d minutes", self._interval)

    def trigger_now(self) -> None:
        """Trigger an immediate sync run (used by /sync bot command)."""
        self._scheduler.add_job(
            self._sync_fn,
            id=f"{_JOB_ID}_manual",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc),
        )
        logger.info("Manual sync triggered")

    def reschedule(self, minutes: int) -> None:
        """Change the sync interval at runtime."""
        self._scheduler.reschedule_job(
            _JOB_ID,
            trigger="interval",
            minutes=minutes,
        )
        self._interval = minutes
        logger.info("Scheduler rescheduled: syncing every %d minutes", minutes)

    @property
    def interval_minutes(self) -> int:
        return self._interval

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=True)
        logger.info("Scheduler shut down")
