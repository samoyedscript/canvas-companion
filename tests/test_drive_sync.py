"""Tests for drive_sync.py with mocked Google API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from canvas_companion.drive_sync import DriveSync


@pytest.fixture
def mock_drive():
    """Create a DriveSync instance with mocked credentials and service."""
    with (
        patch("canvas_companion.drive_sync.build") as mock_build,
        patch.object(DriveSync, "_load_or_refresh_credentials", return_value=MagicMock()),
    ):
        drive = DriveSync.__new__(DriveSync)
        drive._credentials_path = MagicMock()
        drive._token_path = MagicMock()
        drive._root_folder_name = "Canvas Companion"
        drive._creds = MagicMock()
        drive._root_folder_id = None

        mock_service = MagicMock()
        drive._service = mock_service
        yield drive, mock_service


def test_ensure_root_folder_creates_when_missing(mock_drive):
    drive, service = mock_drive

    # No existing folder
    service.files().list().execute.return_value = {"files": []}
    # Create returns new folder
    service.files().create().execute.return_value = {"id": "root_folder_123"}

    folder_id = drive.ensure_root_folder()
    assert folder_id == "root_folder_123"


def test_ensure_root_folder_reuses_existing(mock_drive):
    drive, service = mock_drive

    # Existing folder found
    service.files().list().execute.return_value = {
        "files": [{"id": "existing_root", "name": "Canvas Companion"}]
    }

    folder_id = drive.ensure_root_folder()
    assert folder_id == "existing_root"


def test_ensure_course_folder_creates(mock_drive):
    drive, service = mock_drive

    # No existing subfolder
    service.files().list().execute.return_value = {"files": []}
    service.files().create().execute.return_value = {"id": "course_folder_456"}

    folder_id = drive.ensure_course_folder("CS101", "root_folder_123")
    assert folder_id == "course_folder_456"


def test_upload_file(mock_drive):
    drive, service = mock_drive

    service.files().create().execute.return_value = {
        "id": "uploaded_file_789",
        "webViewLink": "https://drive.google.com/file/789",
    }

    file_id, link = drive.upload_file(
        "lecture.pdf", b"content", "application/pdf", "parent_folder",
    )
    assert file_id == "uploaded_file_789"
    assert link == "https://drive.google.com/file/789"


def test_update_file(mock_drive):
    drive, service = mock_drive

    service.files().update().execute.return_value = {
        "id": "existing_file_789",
        "webViewLink": "https://drive.google.com/file/789v2",
    }

    file_id, link = drive.update_file(
        "existing_file_789", "lecture.pdf", b"new content", "application/pdf",
    )
    assert file_id == "existing_file_789"
    assert link == "https://drive.google.com/file/789v2"
