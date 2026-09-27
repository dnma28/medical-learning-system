from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .session import SourceSpineRef


class SourceContextUnavailable(RuntimeError):
    """Raised when an exact, source-grounded HỌC90 passage cannot be resolved."""


class ResolvedSourceContext(BaseModel):
    source_ref: SourceSpineRef
    evidence_ids: list[str] = Field(default_factory=list)
    passages: list[str] = Field(min_length=1)
    page_start: int | None = None
    page_end: int | None = None


def _data(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


class SupabaseHoc90SourceContextResolver:
    """Resolve exact evidence linked to one Source Map node.

    This deliberately fails closed. It does not perform semantic search, page-range
    guessing, or cross-source substitution when the exact node has no linked evidence.
    """

    LINKS = "mls_evidence_structure_links"
    EVIDENCE = "mls_evidence_blocks"

    def __init__(self, client: Any, *, max_chars: int = 60_000):
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        self.client = client
        self.max_chars = max_chars

    def resolve(self, source_ref: SourceSpineRef) -> ResolvedSourceContext:
        source_id = source_ref.source_id
        node_id = source_ref.source_map_node_id
        if not source_id or not node_id:
            raise SourceContextUnavailable(
                "Source context requires both source_id and source_map_node_id."
            )

        link_rows = _data(
            self.client.table(self.LINKS)
            .select("evidence_id,confidence")
            .eq("source_id", source_id)
            .eq("node_id", node_id)
            .order("confidence", desc=True)
            .execute()
        )
        evidence_ids = list(
            dict.fromkeys(str(row["evidence_id"]) for row in link_rows if row.get("evidence_id"))
        )

        rows: list[dict[str, Any]]
        if evidence_ids:
            rows = _data(
                self.client.table(self.EVIDENCE)
                .select("evidence_id,page_index,block_index,content_type,text")
                .eq("source_id", source_id)
                .in_("evidence_id", evidence_ids)
                .order("page_index")
                .order("block_index")
                .execute()
            )
        else:
            # Backward-compatible exact scalar alignment only. We intentionally do
            # not fall back to page ranges or semantic search because those can
            # silently widen the source boundary.
            rows = _data(
                self.client.table(self.EVIDENCE)
                .select("evidence_id,page_index,block_index,content_type,text")
                .eq("source_id", source_id)
                .eq("structure_node_id", node_id)
                .order("page_index")
                .order("block_index")
                .execute()
            )
            evidence_ids = [
                str(row["evidence_id"]) for row in rows if row.get("evidence_id")
            ]

        text_rows = [
            row for row in rows
            if row.get("content_type") == "text" and str(row.get("text") or "").strip()
        ]
        if not text_rows:
            raise SourceContextUnavailable(
                "No exact text evidence is linked to the requested Source Map node."
            )

        passages = [str(row["text"]).strip() for row in text_rows]
        joined = "\n\n".join(passages)
        if len(joined) > self.max_chars:
            raise SourceContextUnavailable(
                "Resolved source context is too large for one DeepTutor interaction; "
                "use a smaller subsection/source-map node."
            )

        pages = [
            int(row["page_index"])
            for row in text_rows
            if isinstance(row.get("page_index"), int)
        ]
        return ResolvedSourceContext(
            source_ref=source_ref,
            evidence_ids=evidence_ids,
            passages=passages,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
        )
