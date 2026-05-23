"""Google Drive uploader using a Service Account.

Credentials are read from the GOOGLE_SERVICE_ACCOUNT_JSON environment variable
(full JSON content of the service account key file).

IMPORTANT: all API calls include supportsAllDrives=True so that the Service
Account can write to shared folders/Shared Drives (Service Accounts have no
personal storage quota and require this flag for every files.create / files.list
/ files.update call).

Folder structure created automatically:
  BOE-Tracker/          ← root folder (GOOGLE_DRIVE_FOLDER_ID)
    {YYYY}/
      {MM}/
        {DD}/
          {BULLETIN_ID}/
            sumario.json
            pdfs/
              {act_id}.pdf
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaInMemoryUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_JSON = "application/json"
MIME_PDF = "application/pdf"

ENV_SA_JSON = "GOOGLE_SERVICE_ACCOUNT_JSON"
ENV_ROOT_FOLDER = "GOOGLE_DRIVE_FOLDER_ID"

# Required for Service Accounts operating on shared folders / Shared Drives
_SHARED = {
    "supportsAllDrives": True,
    "includeItemsFromAllDrives": True,
}


def _build_service():
    sa_json = os.environ.get(ENV_SA_JSON)
    if not sa_json:
        raise EnvironmentError(f"Environment variable {ENV_SA_JSON} is not set.")
    info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class DriveUploader:
    def __init__(self):
        self.service = _build_service()
        self.root_folder_id: str = os.environ.get(ENV_ROOT_FOLDER, "")
        if not self.root_folder_id:
            raise EnvironmentError(f"Environment variable {ENV_ROOT_FOLDER} is not set.")
        self._folder_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_sumario(
        self, bulletin_id: str, pub_date: str, acts: list[dict]
    ) -> Optional[str]:
        """Upload sumario.json for a bulletin. Returns Drive file ID."""
        folder_id = self._ensure_bulletin_folder(bulletin_id, pub_date)
        content = json.dumps(
            {"bulletin": bulletin_id, "date": pub_date, "acts": acts},
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        return self._upload_bytes(folder_id, "sumario.json", content, MIME_JSON)

    def upload_pdf(
        self, bulletin_id: str, pub_date: str, local_path: Path
    ) -> Optional[str]:
        """Upload a PDF file. Returns Drive file ID."""
        pdf_folder_id = self._ensure_pdf_folder(bulletin_id, pub_date)
        return self._upload_file(pdf_folder_id, local_path, MIME_PDF)

    # ------------------------------------------------------------------
    # Folder management
    # ------------------------------------------------------------------

    def _ensure_bulletin_folder(self, bulletin_id: str, pub_date: str) -> str:
        year, month, day = pub_date.split("-")
        year_id = self._get_or_create_folder(year, self.root_folder_id)
        month_id = self._get_or_create_folder(month, year_id)
        day_id = self._get_or_create_folder(day, month_id)
        return self._get_or_create_folder(bulletin_id, day_id)

    def _ensure_pdf_folder(self, bulletin_id: str, pub_date: str) -> str:
        return self._get_or_create_folder(
            "pdfs", self._ensure_bulletin_folder(bulletin_id, pub_date)
        )

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        cache_key = f"{parent_id}/{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        query = (
            f"name='{name}' and mimeType='{MIME_FOLDER}' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        try:
            results = (
                self.service.files()
                .list(
                    q=query,
                    fields="files(id,name)",
                    spaces="drive",
                    **_SHARED,
                )
                .execute()
            )
            files = results.get("files", [])
            if files:
                folder_id = files[0]["id"]
                self._folder_cache[cache_key] = folder_id
                return folder_id
        except HttpError as exc:
            logger.error("Drive API error searching for folder '%s': %s", name, exc)
            raise

        metadata = {
            "name": name,
            "mimeType": MIME_FOLDER,
            "parents": [parent_id],
        }
        try:
            folder = (
                self.service.files()
                .create(body=metadata, fields="id", **_SHARED)
                .execute()
            )
            folder_id = folder["id"]
            self._folder_cache[cache_key] = folder_id
            logger.debug("Created Drive folder '%s' → %s", name, folder_id)
            return folder_id
        except HttpError as exc:
            logger.error("Drive API error creating folder '%s': %s", name, exc)
            raise

    # ------------------------------------------------------------------
    # File upload
    # ------------------------------------------------------------------

    def _upload_bytes(
        self, folder_id: str, name: str, content: bytes, mime: str
    ) -> Optional[str]:
        existing_id = self._find_file(name, folder_id)
        media = MediaInMemoryUpload(content, mimetype=mime, resumable=False)
        try:
            if existing_id:
                file = (
                    self.service.files()
                    .update(
                        fileId=existing_id,
                        media_body=media,
                        fields="id",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
                logger.info("Updated Drive file: %s", name)
            else:
                file = (
                    self.service.files()
                    .create(
                        body={"name": name, "parents": [folder_id]},
                        media_body=media,
                        fields="id",
                        **_SHARED,
                    )
                    .execute()
                )
                logger.info("Uploaded Drive file: %s", name)
            return file["id"]
        except HttpError as exc:
            logger.error("Failed to upload %s: %s", name, exc)
            return None

    def _upload_file(
        self, folder_id: str, local_path: Path, mime: str
    ) -> Optional[str]:
        name = local_path.name
        existing_id = self._find_file(name, folder_id)
        media = MediaFileUpload(str(local_path), mimetype=mime, resumable=True)
        try:
            if existing_id:
                file = (
                    self.service.files()
                    .update(
                        fileId=existing_id,
                        media_body=media,
                        fields="id",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
                logger.info("Updated Drive file: %s", name)
            else:
                file = (
                    self.service.files()
                    .create(
                        body={"name": name, "parents": [folder_id]},
                        media_body=media,
                        fields="id",
                        **_SHARED,
                    )
                    .execute()
                )
                logger.info("Uploaded Drive file: %s", name)
            return file["id"]
        except HttpError as exc:
            logger.error("Failed to upload %s: %s", name, exc)
            return None

    def _find_file(self, name: str, parent_id: str) -> Optional[str]:
        query = (
            f"name='{name}' and '{parent_id}' in parents "
            f"and trashed=false and mimeType!='{MIME_FOLDER}'"
        )
        try:
            results = (
                self.service.files()
                .list(
                    q=query,
                    fields="files(id,name)",
                    spaces="drive",
                    **_SHARED,
                )
                .execute()
            )
            files = results.get("files", [])
            return files[0]["id"] if files else None
        except HttpError:
            return None
