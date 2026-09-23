from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from .compiler import CompilationOutcome, IncrementalSourceCompiler
from .drive_metadata import DriveFileMetadata
from .source_registry import SourceRecord


DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
PDF_MIME_TYPE = "application/pdf"


class DriveSourceError(RuntimeError):
    pass


class Downloader(Protocol):
    def next_chunk(self) -> tuple[Any, bool]: ...


DownloaderFactory = Callable[[Any, Any], Downloader]


def build_google_drive_service(
    *,
    authorized_user_json: str | None = None,
):
    """Build a read-only Drive v3 service using backend credentials.

    Credential resolution:
    1. explicit authorized_user_json
    2. MLS_GOOGLE_DRIVE_OAUTH_JSON
    3. Google Application Default Credentials

    No interactive browser OAuth flow is performed here.
    """
    try:
        import google.auth
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google Drive support is not installed. "
            "Install with: pip install -e '.[google-drive]'"
        ) from exc

    raw = authorized_user_json or os.getenv("MLS_GOOGLE_DRIVE_OAUTH_JSON")
    if raw:
        info = json.loads(raw)
        credentials = Credentials.from_authorized_user_info(
            info,
            scopes=[DRIVE_READONLY_SCOPE],
        )
    else:
        credentials, _ = google.auth.default(scopes=[DRIVE_READONLY_SCOPE])

    return build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


class GoogleDriveSourceFetcher:
    """Read-only materializer for private PDF blob files in Google Drive."""

    METADATA_FIELDS = (
        "id,name,mimeType,size,modifiedTime,"
        "capabilities(canDownload)"
    )

    def __init__(
        self,
        service: Any,
        *,
        downloader_factory: DownloaderFactory | None = None,
    ):
        self.service = service
        self._downloader_factory = (
            downloader_factory or _google_downloader_factory
        )

    def get_metadata(self, file_id: str) -> DriveFileMetadata:
        raw = self._get_raw_metadata(file_id)
        return DriveFileMetadata(
            file_id=raw["id"],
            title=raw["name"],
            mime_type=raw["mimeType"],
            modified_time=raw["modifiedTime"],
            size_bytes=int(raw["size"]) if raw.get("size") is not None else None,
        )

    @contextmanager
    def materialize_pdf(
        self,
        file_id: str,
        *,
        directory: Path | None = None,
    ) -> Iterator[Path]:
        raw = self._get_raw_metadata(file_id)
        _validate_downloadable_pdf(raw)

        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)

        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".pdf",
            prefix="mls-drive-",
            dir=directory,
            delete=False,
        )
        path = Path(handle.name)
        try:
            request = self.service.files().get_media(
                fileId=file_id,
                supportsAllDrives=True,
            )
            downloader = self._downloader_factory(handle, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            handle.flush()
            handle.close()

            expected_size = (
                int(raw["size"]) if raw.get("size") is not None else None
            )
            if expected_size is not None and path.stat().st_size != expected_size:
                raise DriveSourceError(
                    f"downloaded size mismatch for {file_id}: "
                    f"expected {expected_size}, got {path.stat().st_size}"
                )

            yield path
        finally:
            if not handle.closed:
                handle.close()
            path.unlink(missing_ok=True)

    def _get_raw_metadata(self, file_id: str) -> dict[str, Any]:
        if not file_id.strip():
            raise ValueError("file_id cannot be empty")
        return (
            self.service.files()
            .get(
                fileId=file_id,
                fields=self.METADATA_FIELDS,
                supportsAllDrives=True,
            )
            .execute()
        )


def compile_drive_source(
    compiler: IncrementalSourceCompiler,
    fetcher: GoogleDriveSourceFetcher,
    source: SourceRecord,
    *,
    temp_directory: Path | None = None,
) -> CompilationOutcome:
    """Refresh Drive metadata, materialize privately, then compile once."""
    if source.provider != "google_drive":
        raise ValueError("source provider must be google_drive")

    metadata = fetcher.get_metadata(source.provider_file_id)
    refreshed = source.model_copy(
        update={
            "title": metadata.title,
            "mime_type": metadata.mime_type,
            "size_bytes": metadata.size_bytes,
            "modified_time": metadata.modified_time,
        }
    )

    with fetcher.materialize_pdf(
        source.provider_file_id,
        directory=temp_directory,
    ) as path:
        return compiler.compile(refreshed, path)


def _validate_downloadable_pdf(raw: dict[str, Any]) -> None:
    if raw.get("mimeType") != PDF_MIME_TYPE:
        raise DriveSourceError(
            f"Drive source is not a PDF blob: {raw.get('mimeType')!r}"
        )

    capabilities = raw.get("capabilities") or {}
    if capabilities.get("canDownload") is not True:
        raise PermissionError("Google Drive source cannot be downloaded")


def _google_downloader_factory(handle: Any, request: Any) -> Downloader:
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as exc:
        raise RuntimeError(
            "Google Drive support is not installed. "
            "Install with: pip install -e '.[google-drive]'"
        ) from exc
    return MediaIoBaseDownload(handle, request)
