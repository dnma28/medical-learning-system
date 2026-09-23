from __future__ import annotations

from typing import Any

from .evidence_alignment import (
    AlignmentMethod,
    EvidenceStructureLink,
)


class SupabaseAlignmentStore:
    """Cloud persistence for derived evidence-to-structure links."""

    TABLE = "mls_evidence_structure_links"

    def __init__(self, client: Any):
        self.client = client

    def replace_source(
        self,
        source_id: str,
        links: list[EvidenceStructureLink],
    ) -> None:
        if any(link.source_id != source_id for link in links):
            raise ValueError("all links must belong to source_id")

        self.client.table(self.TABLE).delete().eq(
            "source_id", source_id
        ).execute()
        if links:
            self.client.table(self.TABLE).upsert(
                [
                    {
                        "evidence_id": link.evidence_id,
                        "source_id": link.source_id,
                        "node_id": link.node_id,
                        "method": link.method.value,
                        "confidence": link.confidence,
                    }
                    for link in links
                ],
                on_conflict="evidence_id,node_id",
            ).execute()

    def list_evidence(self, evidence_id: str) -> list[EvidenceStructureLink]:
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("evidence_id", evidence_id)
            .order("confidence", desc=True)
            .execute()
        )
        return [_row_to_link(row) for row in _data(response)]

    def list_node(
        self,
        source_id: str,
        node_id: str,
    ) -> list[EvidenceStructureLink]:
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("source_id", source_id)
            .eq("node_id", node_id)
            .order("confidence", desc=True)
            .execute()
        )
        return [_row_to_link(row) for row in _data(response)]


def _row_to_link(row: dict[str, Any]) -> EvidenceStructureLink:
    return EvidenceStructureLink(
        evidence_id=row["evidence_id"],
        source_id=row["source_id"],
        node_id=row["node_id"],
        method=AlignmentMethod(row["method"]),
        confidence=float(row["confidence"]),
    )


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])
