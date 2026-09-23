from __future__ import annotations

from datetime import datetime
from typing import Any

from .compilation_planner import (
    CompilationJob,
    CompilationTier,
    QueueStatus,
)


class SupabaseCompilationQueueStore:
    """Atomic cloud queue operations implemented by Postgres RPCs."""

    def __init__(self, client: Any):
        self.client = client

    def claim_next(self) -> CompilationJob | None:
        response = self.client.rpc(
            "mls_claim_compilation_job",
            {},
        ).execute()
        rows = _data(response)
        return _job_from_row(rows[0]) if rows else None

    def finish(self, job_id: str, *, success: bool) -> CompilationJob:
        response = self.client.rpc(
            "mls_finish_compilation_job",
            {
                "target_job_id": job_id,
                "was_successful": success,
            },
        ).execute()
        rows = _data(response)
        if not rows:
            raise ValueError(
                f"job is missing or is not running: {job_id}"
            )
        return _job_from_row(rows[0])


def _job_from_row(row: dict[str, Any]) -> CompilationJob:
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


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])
