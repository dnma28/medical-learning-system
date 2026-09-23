from contextlib import contextmanager
from datetime import datetime, timezone

from medical_learning_system.compilation_planner import (
    CompilationJob,
    CompilationTier,
    QueueStatus,
)
from medical_learning_system.compiler import (
    CompilationAction,
    CompilationManifest,
    CompilationOutcome,
    CompilationStatus,
    CompilationStrategy,
)
from medical_learning_system.drive_metadata import DriveFileMetadata
from medical_learning_system.source_registry import (
    SourceKind,
    SourceRecord,
)
from medical_learning_system.worker import (
    CompilationWorker,
    WorkerAction,
)


def job():
    now = datetime(2026, 9, 23, tzinfo=timezone.utc)
    return CompilationJob(
        job_id="job-1",
        source_id="source-1",
        tier=CompilationTier.CORE,
        status=QueueStatus.RUNNING,
        priority=320,
        attempts=1,
        max_attempts=3,
        requested_at=now,
        updated_at=now,
    )


def source():
    return SourceRecord(
        source_id="source-1",
        logical_source_id="costanzo-physiology",
        provider="google_drive",
        provider_file_id="drive-1",
        title="old.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        modified_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
        domain="physiology",
        edition="6",
    )


class Queue:
    def __init__(self, claimed):
        self.claimed = claimed
        self.finished = []

    def claim_next(self):
        value = self.claimed
        self.claimed = None
        return value

    def finish(self, job_id, *, success):
        self.finished.append((job_id, success))
        result = job()
        result.status = (
            QueueStatus.SUCCEEDED if success else QueueStatus.FAILED
        )
        return result


class Sources:
    def __init__(self, value):
        self.value = value

    def get_source(self, source_id):
        return self.value


class Fetcher:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path

    def get_metadata(self, file_id):
        return DriveFileMetadata(
            file_id=file_id,
            title="Costanzo Physiology.pdf",
            mime_type="application/pdf",
            size_bytes=7,
            modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
        )

    @contextmanager
    def materialize_pdf(self, file_id, *, directory=None):
        path = self.tmp_path / "private.pdf"
        path.write_bytes(b"private")
        try:
            yield path
        finally:
            path.unlink(missing_ok=True)


class Compiler:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.received = None

    def compile(self, source_record, path):
        if self.fail:
            raise RuntimeError("private path must not be exposed")
        self.received = (source_record, path.read_bytes())
        manifest = CompilationManifest(
            run_id="run-1",
            source_id=source_record.source_id,
            content_sha256="a" * 64,
            strategy=CompilationStrategy.NATIVE_PDF,
            status=CompilationStatus.SUCCESS,
            structure_nodes=1,
            evidence_blocks=1,
            alignment_links=1,
            grounded_evidence_blocks=1,
            needs_multimodal_enrichment=True,
            created_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        )
        return CompilationOutcome(
            action=CompilationAction.COMPILED,
            manifest=manifest,
        )


def test_worker_idle_when_no_job(tmp_path):
    worker = CompilationWorker(
        queue=Queue(None),
        sources=Sources(source()),
        fetcher=Fetcher(tmp_path),
        compiler=Compiler(),
    )

    result = worker.run_once()

    assert result.action == WorkerAction.IDLE


def test_worker_compiles_drive_source_and_finishes_job(tmp_path):
    queue = Queue(job())
    compiler = Compiler()
    worker = CompilationWorker(
        queue=queue,
        sources=Sources(source()),
        fetcher=Fetcher(tmp_path),
        compiler=compiler,
    )

    result = worker.run_once()

    assert result.action == WorkerAction.SUCCEEDED
    assert result.compilation_action == CompilationAction.COMPILED
    assert queue.finished == [("job-1", True)]
    refreshed, payload = compiler.received
    assert refreshed.title == "Costanzo Physiology.pdf"
    assert payload == b"private"
    assert list(tmp_path.iterdir()) == []


def test_worker_marks_job_failed_without_echoing_sensitive_error(tmp_path):
    queue = Queue(job())
    worker = CompilationWorker(
        queue=queue,
        sources=Sources(source()),
        fetcher=Fetcher(tmp_path),
        compiler=Compiler(fail=True),
    )

    result = worker.run_once()

    assert result.action == WorkerAction.FAILED
    assert result.error_type == "RuntimeError"
    assert "private" not in result.model_dump_json()
    assert queue.finished == [("job-1", False)]


def test_worker_marks_missing_source_failed(tmp_path):
    queue = Queue(job())
    worker = CompilationWorker(
        queue=queue,
        sources=Sources(None),
        fetcher=Fetcher(tmp_path),
        compiler=Compiler(),
    )

    result = worker.run_once()

    assert result.action == WorkerAction.FAILED
    assert result.error_type == "KeyError"
    assert queue.finished == [("job-1", False)]
