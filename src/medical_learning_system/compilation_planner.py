from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .source_registry import SourceRecord, SourceStatus


class CompilationTier(str, Enum):
    CORE = "core"
    CURRICULUM = "curriculum"
    ARCHIVE = "archive"


class QueueStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CompilationJob(BaseModel):
    job_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    tier: CompilationTier
    status: QueueStatus = QueueStatus.PENDING
    priority: int
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    requested_at: datetime
    updated_at: datetime


class PlannedSource(BaseModel):
    source_id: str
    tier: CompilationTier
    priority: int


def plan_sources(
    sources: list[SourceRecord],
    tiers: dict[str, CompilationTier],
    *,
    batch_size: int,
    retry_attempts: dict[str, int] | None = None,
    max_attempts: int = 3,
    include_archive: bool = False,
) -> list[PlannedSource]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    retry_attempts = retry_attempts or {}

    planned: list[PlannedSource] = []
    for source in sources:
        tier = tiers.get(source.source_id, CompilationTier.ARCHIVE)
        if tier == CompilationTier.ARCHIVE and not include_archive:
            continue
        if source.status == SourceStatus.COMPILED:
            continue
        if source.status not in {
            SourceStatus.NEW,
            SourceStatus.STALE,
            SourceStatus.ERROR,
        }:
            continue
        if (
            source.status == SourceStatus.ERROR
            and retry_attempts.get(source.source_id, 0) >= max_attempts
        ):
            continue

        planned.append(
            PlannedSource(
                source_id=source.source_id,
                tier=tier,
                priority=_priority(source.status, tier),
            )
        )

    planned.sort(key=lambda item: (-item.priority, item.source_id))
    return planned[:batch_size]


def _priority(status: SourceStatus, tier: CompilationTier) -> int:
    tier_score = {
        CompilationTier.CORE: 300,
        CompilationTier.CURRICULUM: 200,
        CompilationTier.ARCHIVE: 100,
    }[tier]
    status_score = {
        SourceStatus.STALE: 30,
        SourceStatus.NEW: 20,
        SourceStatus.ERROR: 10,
    }[status]
    return tier_score + status_score


class CompilationQueueStore:
    """SQLite queue with one active job per physical source."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS compilation_jobs (
                    job_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    requested_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_job_per_source
                ON compilation_jobs(source_id)
                WHERE status IN ('pending', 'running');

                CREATE INDEX IF NOT EXISTS idx_compilation_jobs_ready
                ON compilation_jobs(status, priority DESC, requested_at);
                """
            )

    def enqueue(
        self,
        source_id: str,
        tier: CompilationTier,
        priority: int,
        *,
        max_attempts: int = 3,
    ) -> CompilationJob:
        now = datetime.now(timezone.utc)
        job = CompilationJob(
            job_id=f"job-{source_id}-{int(now.timestamp() * 1_000_000)}",
            source_id=source_id,
            tier=tier,
            priority=priority,
            max_attempts=max_attempts,
            requested_at=now,
            updated_at=now,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO compilation_jobs (
                        job_id, source_id, tier, status, priority,
                        attempts, max_attempts, requested_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.job_id,
                        job.source_id,
                        job.tier.value,
                        job.status.value,
                        job.priority,
                        job.attempts,
                        job.max_attempts,
                        job.requested_at.isoformat(),
                        job.updated_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"active job already exists for {source_id}") from exc
        return job

    def enqueue_plan(
        self,
        plan: list[PlannedSource],
        *,
        max_attempts: int = 3,
    ) -> list[CompilationJob]:
        jobs = []
        for item in plan:
            jobs.append(
                self.enqueue(
                    item.source_id,
                    item.tier,
                    item.priority,
                    max_attempts=max_attempts,
                )
            )
        return jobs

    def claim_next(self) -> CompilationJob | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM compilation_jobs
                WHERE status = 'pending'
                  AND attempts < max_attempts
                ORDER BY priority DESC, requested_at, job_id
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                UPDATE compilation_jobs
                SET status = 'running',
                    attempts = attempts + 1,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (now, row["job_id"]),
            )
            updated = connection.execute(
                "SELECT * FROM compilation_jobs WHERE job_id = ?",
                (row["job_id"],),
            ).fetchone()
        return self._row(updated)

    def finish(self, job_id: str, *, success: bool) -> CompilationJob:
        status = QueueStatus.SUCCEEDED if success else QueueStatus.FAILED
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM compilation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] != QueueStatus.RUNNING.value:
                raise ValueError("only running jobs can be finished")
            connection.execute(
                """
                UPDATE compilation_jobs
                SET status = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status.value, now, job_id),
            )
            updated = connection.execute(
                "SELECT * FROM compilation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row(updated)

    def retry_failed(self, job_id: str) -> CompilationJob:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM compilation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] != QueueStatus.FAILED.value:
                raise ValueError("only failed jobs can be retried")
            if row["attempts"] >= row["max_attempts"]:
                raise ValueError("max attempts reached")
            connection.execute(
                """
                UPDATE compilation_jobs
                SET status = 'pending', updated_at = ?
                WHERE job_id = ?
                """,
                (now, job_id),
            )
            updated = connection.execute(
                "SELECT * FROM compilation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row(updated)

    @staticmethod
    def _row(row: sqlite3.Row) -> CompilationJob:
        return CompilationJob(
            job_id=row["job_id"],
            source_id=row["source_id"],
            tier=CompilationTier(row["tier"]),
            status=QueueStatus(row["status"]),
            priority=row["priority"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            requested_at=datetime.fromisoformat(row["requested_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
