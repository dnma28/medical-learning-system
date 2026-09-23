from datetime import datetime, timezone

import pytest

from medical_learning_system.compilation_planner import (
    CompilationQueueStore,
    CompilationTier,
    QueueStatus,
    plan_sources,
)
from medical_learning_system.source_registry import (
    SourceKind,
    SourceRecord,
    SourceStatus,
)


def source(source_id, status):
    return SourceRecord(
        source_id=source_id,
        logical_source_id=source_id,
        provider="local",
        provider_file_id=source_id,
        title=f"{source_id}.pdf",
        mime_type="application/pdf",
        modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
        status=status,
    )


def test_core_sources_outrank_curriculum_and_archive_is_excluded():
    sources = [
        source("core-new", SourceStatus.NEW),
        source("curriculum-stale", SourceStatus.STALE),
        source("archive-new", SourceStatus.NEW),
    ]
    plan = plan_sources(
        sources,
        {
            "core-new": CompilationTier.CORE,
            "curriculum-stale": CompilationTier.CURRICULUM,
            "archive-new": CompilationTier.ARCHIVE,
        },
        batch_size=10,
    )

    assert [item.source_id for item in plan] == [
        "core-new",
        "curriculum-stale",
    ]


def test_compiled_sources_are_not_queued_and_batch_is_bounded():
    sources = [
        source("compiled", SourceStatus.COMPILED),
        source("a", SourceStatus.NEW),
        source("b", SourceStatus.NEW),
    ]
    plan = plan_sources(
        sources,
        {"a": CompilationTier.CORE, "b": CompilationTier.CORE},
        batch_size=1,
    )
    assert len(plan) == 1
    assert plan[0].source_id == "a"


def test_error_source_stops_after_max_attempts():
    plan = plan_sources(
        [source("error", SourceStatus.ERROR)],
        {"error": CompilationTier.CORE},
        batch_size=10,
        retry_attempts={"error": 3},
        max_attempts=3,
    )
    assert plan == []


def test_queue_prevents_duplicate_active_jobs(tmp_path):
    store = CompilationQueueStore(tmp_path / "queue.sqlite3")
    store.enqueue("source-1", CompilationTier.CORE, 320)

    with pytest.raises(ValueError, match="active job"):
        store.enqueue("source-1", CompilationTier.CORE, 320)


def test_queue_claims_highest_priority_and_tracks_attempts(tmp_path):
    store = CompilationQueueStore(tmp_path / "queue.sqlite3")
    store.enqueue("curriculum", CompilationTier.CURRICULUM, 220)
    store.enqueue("core", CompilationTier.CORE, 320)

    job = store.claim_next()

    assert job.source_id == "core"
    assert job.status == QueueStatus.RUNNING
    assert job.attempts == 1


def test_failed_job_can_retry_until_limit(tmp_path):
    store = CompilationQueueStore(tmp_path / "queue.sqlite3")
    job = store.enqueue(
        "source-1",
        CompilationTier.CORE,
        320,
        max_attempts=2,
    )

    first = store.claim_next()
    store.finish(first.job_id, success=False)
    store.retry_failed(job.job_id)
    second = store.claim_next()
    failed = store.finish(second.job_id, success=False)

    assert failed.attempts == 2
    with pytest.raises(ValueError, match="max attempts"):
        store.retry_failed(job.job_id)
