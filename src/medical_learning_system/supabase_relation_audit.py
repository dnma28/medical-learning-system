from __future__ import annotations

from datetime import datetime
from typing import Any

from .knowledge_graph.relation_audit_ledger import (
    RelationAuditDecisionRecord,
)
from .knowledge_graph.relation_support import RelationAuditMappingState


class SupabaseRelationAuditDecisionStore:
    """Append-only production ledger for relation audit decisions."""

    TABLE = "mls_relation_audit_decisions"

    def __init__(self, client: Any):
        self.client = client

    def append(self, record: RelationAuditDecisionRecord) -> None:
        if self.get(record.decision_id) is not None:
            raise ValueError(
                f"decision_id already exists: {record.decision_id}"
            )

        if record.supersedes_decision_id is not None:
            prior = self.get(record.supersedes_decision_id)
            if prior is None:
                raise ValueError(
                    "supersedes_decision_id does not exist: "
                    f"{record.supersedes_decision_id}"
                )
            if prior.mapping_id != record.mapping_id:
                raise ValueError(
                    "superseded decision belongs to a different mapping"
                )

        self.client.table(self.TABLE).insert(
            _decision_to_row(record)
        ).execute()

    def get(
        self,
        decision_id: str,
    ) -> RelationAuditDecisionRecord | None:
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("decision_id", decision_id)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return _decision_from_row(rows[0]) if rows else None

    def history(
        self,
        mapping_id: str,
    ) -> list[RelationAuditDecisionRecord]:
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("mapping_id", mapping_id)
            .order("reviewed_at")
            .order("decision_id")
            .execute()
        )
        return [_decision_from_row(row) for row in _data(response)]

    def latest(
        self,
        mapping_id: str,
    ) -> RelationAuditDecisionRecord | None:
        history = self.history(mapping_id)
        return history[-1] if history else None


def _decision_to_row(
    record: RelationAuditDecisionRecord,
) -> dict[str, Any]:
    return {
        "decision_id": record.decision_id,
        "mapping_id": record.mapping_id,
        "relation_candidate_id": record.relation_candidate_id,
        "audit_id": record.audit_id,
        "state": record.state.value,
        "reviewer": record.reviewer,
        "reviewed_at": record.reviewed_at.isoformat(),
        "note": record.note,
        "supersedes_decision_id": record.supersedes_decision_id,
    }


def _decision_from_row(
    row: dict[str, Any],
) -> RelationAuditDecisionRecord:
    return RelationAuditDecisionRecord(
        decision_id=row["decision_id"],
        mapping_id=row["mapping_id"],
        relation_candidate_id=row["relation_candidate_id"],
        audit_id=row["audit_id"],
        state=RelationAuditMappingState(row["state"]),
        reviewer=row["reviewer"],
        reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
        note=row.get("note"),
        supersedes_decision_id=row.get("supersedes_decision_id"),
    )


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])
