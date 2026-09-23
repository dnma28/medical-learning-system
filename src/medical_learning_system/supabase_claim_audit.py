from __future__ import annotations

from datetime import datetime
from typing import Any

from .knowledge_graph.claim_audit import (
    ClaimAuditRecord,
    ContentFidelityState,
    CurrentValidityState,
    SourceAnchorState,
)


class SupabaseClaimAuditStore:
    """Append-only production store for passage-level claim audits."""

    TABLE = "mls_claim_audits"

    def __init__(self, client: Any):
        self.client = client

    def append(self, record: ClaimAuditRecord) -> None:
        if self.get(record.audit_id) is not None:
            raise ValueError(f"audit_id already exists: {record.audit_id}")

        self.client.table(self.TABLE).insert(
            _audit_to_row(record)
        ).execute()

    def get(self, audit_id: str) -> ClaimAuditRecord | None:
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("audit_id", audit_id)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return _audit_from_row(rows[0]) if rows else None

    def history(
        self,
        patch_id: str,
        claim_text: str,
    ) -> list[ClaimAuditRecord]:
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("patch_id", patch_id)
            .eq("claim_text", claim_text)
            .order("reviewed_at")
            .order("audit_id")
            .execute()
        )
        return [_audit_from_row(row) for row in _data(response)]

    def latest(
        self,
        patch_id: str,
        claim_text: str,
    ) -> ClaimAuditRecord | None:
        history = self.history(patch_id, claim_text)
        return history[-1] if history else None


def _audit_to_row(record: ClaimAuditRecord) -> dict[str, Any]:
    return {
        "audit_id": record.audit_id,
        "patch_id": record.patch_id,
        "claim_text": record.claim_text,
        "source_anchor_id": record.source_anchor_id,
        "source_anchor_state": record.source_anchor_state.value,
        "evidence_candidate_ids": sorted(record.evidence_candidate_ids),
        "selected_evidence_ids": sorted(record.selected_evidence_ids),
        "content_fidelity_state": record.content_fidelity_state.value,
        "current_validity_state": record.current_validity_state.value,
        "requires_current_check": record.requires_current_check,
        "reviewer": record.reviewer,
        "review_method": record.review_method,
        "reviewed_at": record.reviewed_at.isoformat(),
        "supersedes_audit_id": record.supersedes_audit_id,
        "notes": record.notes,
    }


def _audit_from_row(row: dict[str, Any]) -> ClaimAuditRecord:
    return ClaimAuditRecord(
        audit_id=row["audit_id"],
        patch_id=row["patch_id"],
        claim_text=row["claim_text"],
        source_anchor_id=row["source_anchor_id"],
        source_anchor_state=SourceAnchorState(row["source_anchor_state"]),
        evidence_candidate_ids=set(row.get("evidence_candidate_ids") or []),
        selected_evidence_ids=set(row.get("selected_evidence_ids") or []),
        content_fidelity_state=ContentFidelityState(
            row["content_fidelity_state"]
        ),
        current_validity_state=CurrentValidityState(
            row["current_validity_state"]
        ),
        requires_current_check=bool(row["requires_current_check"]),
        reviewer=row["reviewer"],
        review_method=row["review_method"],
        reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
        supersedes_audit_id=row.get("supersedes_audit_id"),
        notes=list(row.get("notes") or []),
    )


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])
