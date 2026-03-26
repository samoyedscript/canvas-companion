"""Google Drive folder and file management via the official Python client."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events",
]
_FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveSync:
    def __init__(
        self,
        credentials_path: Path,
        token_path: Path,
        root_folder_name: str,
    ) -> None:
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._root_folder_name = root_folder_name
        self._creds = self._load_or_refresh_credentials()
        self._service = build("drive", "v3", credentials=self._creds)
        self._root_folder_id: str | None = None

    @property
    def credentials(self) -> Credentials:
        """Expose OAuth credentials for reuse by other Google API services."""
        return self._creds

    def _load_or_refresh_credentials(self) -> Credentials:
        """Load token.json if valid; refresh if expired; run OAuth flow if absent."""
        creds: Credentials | None = None

        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)

        if creds and creds.valid:
            # Check if all required scopes are present
            if creds.scopes and set(SCOPES).issubset(set(creds.scopes)):
                return creds
            logger.info(
                "Re-authorization required: token missing scopes %s",
                set(SCOPES) - set(creds.scopes or []),
            )
            creds = None  # Fall through to OAuth flow

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self._credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save the refreshed/new token
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())
        return creds

    def _find_folder(self, name: str, parent_id: str | None = None) -> str | None:
        """Search for a folder by name, optionally within a parent. Returns folder ID or None."""
        escaped_name = name.replace("\\", "\\\\").replace("'", "\\'")
        query = f"name = '{escaped_name}' and mimeType = '{_FOLDER_MIME}' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = (
            self._service.files()
            .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
            .execute()
        )
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def _create_folder(self, name: str, parent_id: str | None = None) -> str:
        """Create a folder and return its ID."""
        metadata: dict = {"name": name, "mimeType": _FOLDER_MIME}
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = (
            self._service.files()
            .create(body=metadata, fields="id")
            .execute()
        )
        folder_id = folder["id"]
        logger.info("Created Drive folder '%s' (id=%s)", name, folder_id)
        return folder_id

    def ensure_root_folder(self) -> str:
        """Find or create the root folder. Return folder ID."""
        if self._root_folder_id:
            return self._root_folder_id

        folder_id = self._find_folder(self._root_folder_name)
        if folder_id is None:
            folder_id = self._create_folder(self._root_folder_name)
        self._root_folder_id = folder_id
        return folder_id

    def ensure_course_folder(self, course_name: str, root_folder_id: str) -> str:
        """Find or create a per-course subfolder. Return folder ID."""
        folder_id = self._find_folder(course_name, parent_id=root_folder_id)
        if folder_id is None:
            folder_id = self._create_folder(course_name, parent_id=root_folder_id)
        return folder_id

    def upload_file(
        self,
        file_name: str,
        content: bytes,
        mime_type: str | None,
        parent_folder_id: str,
    ) -> tuple[str, str]:
        """Upload a new file. Return (drive_file_id, web_view_link)."""
        metadata = {"name": file_name, "parents": [parent_folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype=mime_type or "application/octet-stream",
            resumable=True,
        )
        result = (
            self._service.files()
            .create(body=metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )
        logger.info("Uploaded '%s' to Drive (id=%s)", file_name, result["id"])
        return result["id"], result.get("webViewLink", "")

    def update_file(
        self,
        drive_file_id: str,
        file_name: str,
        content: bytes,
        mime_type: str | None,
    ) -> tuple[str, str]:
        """Update an existing file's content. Return (drive_file_id, web_view_link)."""
        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype=mime_type or "application/octet-stream",
            resumable=True,
        )
        result = (
            self._service.files()
            .update(
                fileId=drive_file_id,
                body={"name": file_name},
                media_body=media,
                fields="id, webViewLink",
            )
            .execute()
        )
        logger.info("Updated '%s' on Drive (id=%s)", file_name, result["id"])
        return result["id"], result.get("webViewLink", "")
