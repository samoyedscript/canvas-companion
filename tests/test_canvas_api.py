"""Tests for canvas_api.py using httpx mock transport."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from canvas_companion.canvas_api import CanvasClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "canvas"


def _load_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES_DIR / name).read_text())


def _mock_transport(routes: dict[str, tuple[int, dict | list]]) -> httpx.MockTransport:
    """Create a mock transport that returns predefined responses for URL patterns."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for pattern, (status, body) in routes.items():
            if pattern in path:
                return httpx.Response(
                    status_code=status,
                    json=body,
                    headers={"content-type": "application/json"},
                )
        return httpx.Response(status_code=404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_get_active_courses():
    courses_data = _load_fixture("courses.json")
    transport = _mock_transport({"/courses": (200, courses_data)})

    client = CanvasClient.__new__(CanvasClient)
    client._base_url = "https://canvas.test.edu"
    client._client = httpx.AsyncClient(
        base_url="https://canvas.test.edu/api/v1",
        transport=transport,
    )

    courses = await client.get_active_courses()
    assert len(courses) == 2
    assert courses[0].id == 101
    assert courses[0].name == "Introduction to Computer Science"
    assert courses[1].course_code == "CS202"

    await client.close()


@pytest.mark.asyncio
async def test_get_assignments():
    assignments_data = _load_fixture("assignments.json")
    transport = _mock_transport({"/assignments": (200, assignments_data)})

    client = CanvasClient.__new__(CanvasClient)
    client._base_url = "https://canvas.test.edu"
    client._client = httpx.AsyncClient(
        base_url="https://canvas.test.edu/api/v1",
        transport=transport,
    )

    assignments = await client.get_assignments(101)
    assert len(assignments) == 2
    assert assignments[0].name == "Homework 1"
    assert assignments[0].course_id == 101
    assert assignments[1].points_possible == 200.0

    await client.close()


@pytest.mark.asyncio
async def test_get_announcements():
    announcements_data = _load_fixture("announcements.json")
    transport = _mock_transport({"/announcements": (200, announcements_data)})

    client = CanvasClient.__new__(CanvasClient)
    client._base_url = "https://canvas.test.edu"
    client._client = httpx.AsyncClient(
        base_url="https://canvas.test.edu/api/v1",
        transport=transport,
    )

    announcements = await client.get_announcements([101])
    assert len(announcements) == 1
    assert announcements[0].title == "Welcome to CS101"
    assert announcements[0].course_id == 101

    await client.close()


@pytest.mark.asyncio
async def test_get_files():
    files_data = _load_fixture("files.json")
    transport = _mock_transport({"/files": (200, files_data)})

    client = CanvasClient.__new__(CanvasClient)
    client._base_url = "https://canvas.test.edu"
    client._client = httpx.AsyncClient(
        base_url="https://canvas.test.edu/api/v1",
        transport=transport,
    )

    files = await client.get_files(101)
    assert len(files) == 2
    assert files[0].display_name == "lecture01.pdf"
    assert files[0].course_id == 101
    assert files[1].size == 2097152

    await client.close()


@pytest.mark.asyncio
async def test_get_assignments_403_returns_empty():
    transport = _mock_transport({"/assignments": (403, {"message": "forbidden"})})

    client = CanvasClient.__new__(CanvasClient)
    client._base_url = "https://canvas.test.edu"
    client._client = httpx.AsyncClient(
        base_url="https://canvas.test.edu/api/v1",
        transport=transport,
    )

    assignments = await client.get_assignments(101)
    assert assignments == []

    await client.close()


@pytest.mark.asyncio
async def test_pagination():
    """Test that pagination follows Link: rel=next headers."""
    page1 = [{"id": 1, "name": "Course 1", "course_code": "C1"}]
    page2 = [{"id": 2, "name": "Course 2", "course_code": "C2"}]

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                status_code=200,
                json=page1,
                headers={
                    "content-type": "application/json",
                    "link": '<https://canvas.test.edu/api/v1/courses?page=2>; rel="next"',
                },
            )
        return httpx.Response(
            status_code=200,
            json=page2,
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    client = CanvasClient.__new__(CanvasClient)
    client._base_url = "https://canvas.test.edu"
    client._client = httpx.AsyncClient(
        base_url="https://canvas.test.edu/api/v1",
        transport=transport,
    )

    courses = await client.get_active_courses()
    assert len(courses) == 2
    assert call_count == 2

    await client.close()
