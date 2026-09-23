from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from .compilation_planner import CompilationJob
from .compiler import CompilationAction, IncrementalSourceCompiler
from .drive_source import (
    GoogleDriveSourceFetcher,
    compile_drive_source,
)
from .source_registry import SourceRecord
from .supabase_compiler import build_supabase_native_pdf_compiler
from .supabase_queue import SupabaseCompilationQueueStore
from .supabase_storage import SupabaseMedicalStore


class WorkerAction(str, Enum):
    IDLE = "idle"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkerOutcome(BaseModel):
    action: WorkerAction
    job_id: str | None = None
    source_id: str | None = None
    compilation_action: CompilationAction | None = None
    error_type: str | None = None


class CompilationQueueBackend(Protocol):
    def claim_next(self) -> CompilationJob | None: ...

    def finish(self, job_id: str, *, success: bool) -> CompilationJob: ...


class SourceLookupBackend(Protocol):
    def get_source(self, source_id: str) -> SourceRecord | None: ...


class CompilationWorker:
    """Process at most one already-planned source compilation job."""

    def __init__(
        self,
        *,
        queue: CompilationQueueBackend,
        sources: SourceLookupBackend,
        fetcher: GoogleDriveSourceFetcher,
        compiler: IncrementalSourceCompiler,
        temp_directory: Path | None = None,
    ):
        self.queue = queue
        self.sources = sources
        self.fetcher = fetcher
        self.compiler = compiler
        self.temp_directory = temp_directory

    def run_once(self) -> WorkerOutcome:
        job = self.queue.claim_next()
        if job is None:
            return WorkerOutcome(action=WorkerAction.IDLE)

        try:
            source = self.sources.get_source(job.source_id)
            if source is None:
                raise KeyError("claimed source is not registered")
            if source.provider != "google_drive":
                raise ValueError("claimed source provider must be google_drive")

            result = compile_drive_source(
                self.compiler,
                self.fetcher,
                source,
                temp_directory=self.temp_directory,
            )
            self.queue.finish(job.job_id, success=True)
            return WorkerOutcome(
                action=WorkerAction.SUCCEEDED,
                job_id=job.job_id,
                source_id=job.source_id,
                compilation_action=result.action,
            )
        except Exception as exc:
            try:
                self.queue.finish(job.job_id, success=False)
            except Exception as finish_exc:
                raise RuntimeError(
                    "compilation failed and queue finalization also failed"
                ) from finish_exc

            return WorkerOutcome(
                action=WorkerAction.FAILED,
                job_id=job.job_id,
                source_id=job.source_id,
                error_type=exc.__class__.__name__,
            )


def build_supabase_drive_worker(
    client: Any,
    drive_service: Any,
    *,
    temp_directory: Path | None = None,
) -> CompilationWorker:
    medical = SupabaseMedicalStore(client)
    return CompilationWorker(
        queue=SupabaseCompilationQueueStore(client),
        sources=medical,
        fetcher=GoogleDriveSourceFetcher(drive_service),
        compiler=build_supabase_native_pdf_compiler(client),
        temp_directory=temp_directory,
    )
