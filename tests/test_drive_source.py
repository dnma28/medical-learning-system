from datetime import datetime, timezone
from pathlib import Path

import pytest

from medical_learning_system.drive_source import (
    DriveSourceError,
    GoogleDriveSourceFetcher,
    compile_drive_source,
)
from medical_learning_system.source_registry import SourceKind, SourceRecord


PDF_BYTES = b"%PDF-private-test"


class Request:
    def __init__(self, payload=None):
        self.payload = payload

    def execute(self):
        return self.payload


class Files:
    def __init__(self, metadata, payload=PDF_BYTES):
        self.metadata = metadata
        self.payload = payload
        self.media_requests = 0

    def get(self, **kwargs):
        return Request(self.metadata)

    def get_media(self, **kwargs):
        self.media_requests += 1
        return Request(self.payload)


class Service:
    def __init__(self, metadata, payload=PDF_BYTES):
        self.files_api = Files(metadata, payload)

    def files(self):
        return self.files_api


class FakeDownloader:
    def __init__(self, handle, request):
        self.handle = handle
        self.request = request
        self.done = False

    def next_chunk(self):
        if not self.done:
            self.handle.write(self.request.payload)
            self.done = True
        return None, self.done


def metadata(
    *,
    mime_type="application/pdf",
    can_download=True,
    size=len(PDF_BYTES),
):
    return {
        "id": "drive-123",
        "name": "Costanzo Physiology.pdf",
        "mimeType": mime_type,
        "size": str(size),
        "modifiedTime": "2026-09-23T10:00:00Z",
        "capabilities": {"canDownload": can_download},
    }


def fetcher(meta=None, payload=PDF_BYTES):
    service = Service(meta or metadata(), payload)
    return (
        GoogleDriveSourceFetcher(
            service,
            downloader_factory=FakeDownloader,
        ),
        service,
    )


def test_drive_metadata_normalizes_existing_contract():
    source_fetcher, _ = fetcher()

    result = source_fetcher.get_metadata("drive-123")

    assert result.file_id == "drive-123"
    assert result.title == "Costanzo Physiology.pdf"
    assert result.mime_type == "application/pdf"
    assert result.size_bytes == len(PDF_BYTES)
    assert result.modified_time == datetime(
        2026, 9, 23, 10, 0, tzinfo=timezone.utc
    )


def test_materialize_streams_pdf_and_always_deletes_temp_file(tmp_path):
    source_fetcher, service = fetcher()

    with source_fetcher.materialize_pdf(
        "drive-123",
        directory=tmp_path,
    ) as path:
        assert path.read_bytes() == PDF_BYTES
        assert path.parent == tmp_path
        saved_path = path

    assert not saved_path.exists()
    assert service.files_api.media_requests == 1


def test_non_downloadable_source_fails_before_media_request(tmp_path):
    source_fetcher, service = fetcher(metadata(can_download=False))

    with pytest.raises(PermissionError, match="cannot be downloaded"):
        with source_fetcher.materialize_pdf(
            "drive-123",
            directory=tmp_path,
        ):
            pass

    assert service.files_api.media_requests == 0


def test_non_pdf_source_fails_loudly(tmp_path):
    source_fetcher, service = fetcher(
        metadata(mime_type="application/vnd.google-apps.document")
    )

    with pytest.raises(DriveSourceError, match="not a PDF"):
        with source_fetcher.materialize_pdf(
            "drive-123",
            directory=tmp_path,
        ):
            pass

    assert service.files_api.media_requests == 0


def test_size_mismatch_fails_and_cleans_up(tmp_path):
    source_fetcher, _ = fetcher(metadata(size=len(PDF_BYTES) + 1))

    with pytest.raises(DriveSourceError, match="size mismatch"):
        with source_fetcher.materialize_pdf(
            "drive-123",
            directory=tmp_path,
        ):
            pass

    assert list(tmp_path.iterdir()) == []


class Compiler:
    def __init__(self):
        self.received = None

    def compile(self, source, path):
        assert path.exists()
        self.received = (source, path.read_bytes())
        return "compiled"


def source_record():
    return SourceRecord(
        source_id="costanzo-physical",
        logical_source_id="costanzo-physiology",
        provider="google_drive",
        provider_file_id="drive-123",
        title="old-title.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        modified_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
        domain="physiology",
        edition="6",
    )


def test_compile_drive_source_refreshes_metadata_and_preserves_classification(tmp_path):
    source_fetcher, _ = fetcher()
    compiler = Compiler()

    result = compile_drive_source(
        compiler,
        source_fetcher,
        source_record(),
        temp_directory=tmp_path,
    )

    assert result == "compiled"
    refreshed, payload = compiler.received
    assert refreshed.title == "Costanzo Physiology.pdf"
    assert refreshed.size_bytes == len(PDF_BYTES)
    assert refreshed.logical_source_id == "costanzo-physiology"
    assert refreshed.kind == SourceKind.TEXTBOOK
    assert refreshed.edition == "6"
    assert payload == PDF_BYTES
    assert list(tmp_path.iterdir()) == []
