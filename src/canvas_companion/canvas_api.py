"""Canvas LMS REST API client with pagination and retry logic."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from canvas_companion.models import (
    CanvasAnnouncement,
    CanvasAssignment,
    CanvasCourse,
    CanvasFile,
    CanvasSubmission,
)

logger = logging.getLogger(__name__)

_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds


class CanvasClient:
    def __init__(self, base_url: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/v1",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make a request with retry + backoff on 429 and 5xx."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._client.request(method, url, **kwargs)
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < _MAX_RETRIES:
                        wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                        logger.warning(
                            "Canvas API %s %s returned %s, retrying in %.1fs (attempt %d/%d)",
                            method, url, resp.status_code, wait, attempt, _MAX_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        continue
                resp.raise_for_status()
                return resp
            except httpx.TimeoutException:
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "Canvas API %s %s timed out, retrying in %.1fs (attempt %d/%d)",
                        method, url, wait, attempt, _MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
        # Should not reach here, but satisfy type checker
        return resp  # type: ignore[possibly-undefined]

    async def _paginate(self, url: str, params: dict | None = None) -> list[dict]:
        """Follow Link rel='next' headers to collect all pages."""
        results: list[dict] = []
        p = dict(params or {})
        p.setdefault("per_page", "50")

        next_url: str | None = url
        while next_url is not None:
            resp = await self._request("GET", next_url, params=p)
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)

            # After the first request, params are embedded in the next URL
            p = {}
            link_header = resp.headers.get("link", "")
            match = _LINK_NEXT_RE.search(link_header)
            next_url = match.group(1) if match else None

        return results

    async def get_active_courses(self) -> list[CanvasCourse]:
        data = await self._paginate("/courses", {"enrollment_state": "active"})
        courses = []
        for item in data:
            try:
                courses.append(
                    CanvasCourse(
                        id=item["id"],
                        name=item.get("name", ""),
                        course_code=item.get("course_code", ""),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed course: %s", e)
        return courses

    async def get_assignments(self, course_id: int) -> list[CanvasAssignment]:
        try:
            data = await self._paginate(
                f"/courses/{course_id}/assignments",
                {"order_by": "due_at"},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.info("No access to assignments for course %d", course_id)
                return []
            raise
        assignments = []
        for item in data:
            try:
                assignments.append(
                    CanvasAssignment(
                        id=item["id"],
                        course_id=course_id,
                        name=item.get("name", ""),
                        description=item.get("description"),
                        due_at=item.get("due_at"),
                        html_url=item.get("html_url", ""),
                        points_possible=item.get("points_possible"),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed assignment: %s", e)
        return assignments

    async def get_announcements(
        self,
        course_ids: list[int],
        start_date: str | None = None,
    ) -> list[CanvasAnnouncement]:
        if not course_ids:
            return []
        if start_date is None:
            start_date = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")

        context_codes = [f"course_{cid}" for cid in course_ids]
        params: dict = {
            "context_codes[]": context_codes,
            "start_date": start_date,
        }
        try:
            data = await self._paginate("/announcements", params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.info("No access to announcements")
                return []
            raise

        announcements = []
        for item in data:
            try:
                # Extract course_id from context_code like "course_12345"
                context_code = item.get("context_code", "")
                cid = int(context_code.replace("course_", "")) if context_code else 0
                announcements.append(
                    CanvasAnnouncement(
                        id=item["id"],
                        course_id=cid,
                        title=item.get("title", ""),
                        message=item.get("message", ""),
                        posted_at=item["posted_at"],
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed announcement: %s", e)
        return announcements

    async def get_files(self, course_id: int) -> list[CanvasFile]:
        try:
            data = await self._paginate(
                f"/courses/{course_id}/files",
                {"sort": "updated_at", "order": "desc"},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.info("No access to files for course %d", course_id)
                return []
            raise

        files = []
        for item in data:
            try:
                files.append(
                    CanvasFile(
                        id=item["id"],
                        course_id=course_id,
                        display_name=item.get("display_name", ""),
                        url=item.get("url", ""),
                        updated_at=item["updated_at"],
                        size=item.get("size", 0),
                        content_type=item.get("content-type") or item.get("content_type"),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed file: %s", e)
        return files

    async def get_my_submissions(
        self, course_id: int, assignment_ids: list[int],
    ) -> list[CanvasSubmission]:
        """Fetch the authenticated user's submissions for the given assignments."""
        if not assignment_ids:
            return []
        params: dict = {
            "student_ids[]": ["self"],
            "assignment_ids[]": [str(aid) for aid in assignment_ids],
        }
        try:
            data = await self._paginate(
                f"/courses/{course_id}/students/submissions", params,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.info("No access to submissions for course %d", course_id)
                return []
            raise

        submissions = []
        for item in data:
            try:
                submissions.append(
                    CanvasSubmission(
                        assignment_id=item["assignment_id"],
                        workflow_state=item.get("workflow_state", "unsubmitted"),
                        submitted_at=item.get("submitted_at"),
                        late=item.get("late", False),
                        missing=item.get("missing", False),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed submission: %s", e)
        return submissions

    async def download_file(self, file_url: str) -> bytes:
        """Download file content from the pre-signed URL returned by the files endpoint."""
        resp = await self._request("GET", file_url)
        return resp.content
