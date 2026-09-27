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
    """Resolve exact evidence linked to one promoted Source Map node.

    Resolution is deliberately narrow. It never semantic-searches another node,
    guesses a page range, or substitutes another physical source.
    """

    SOURCE_MAP_LINKS = "mls_source_map_evidence_links"
    LEGACY_LINKS = "mls_evidence_structure_links"
    EVIDENCE = "mls_evidence_blocks"

    def __init__(self, client: Any, *, max_chars: int = 60_000):
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        self.client = client
        self.max_chars = max_chars

    def resolve(self, source_ref: SourceSpineRef) -> ResolvedSourceContext:
        source_id = source_ref.source_id
        node_id = source_ref.source_map_node_id
        logical_source_id = source_ref.logical_source_id
        if not source_id or not node_id:
            raise SourceContextUnavailable(
                "Source context requires both source_id and source_map_node_id."
            )

        # Preferred contract: exact promoted Source Map identity.
        link_rows = _data(
            self.client.table(self.SOURCE_MAP_LINKS)
            .select("evidence_id,confidence")
            .eq("logical_source_id", logical_source_id)
            .eq("source_id", source_id)
            .eq("node_id", node_id)
            .order("confidence", desc=True)
            .execute()
        )
        evidence_ids = _unique_evidence_ids(link_rows)

        # Backward compatibility only. This does not widen the source boundary.
        if not evidence_ids:
            legacy_rows = _data(
                self.client.table(self.LEGACY_LINKS)
                .select("evidence_id,confidence")
                .eq("source_id", source_id)
                .eq("node_id", node_id)
                .order("confidence", desc=True)
                .execute()
            )
            evidence_ids = _unique_evidence_ids(legacy_rows)

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
            # Old rows may carry one exact scalar structure_node_id. We do not
            # fall back to page ranges because that can silently widen context.
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
            row
            for row in rows
            if row.get("content_type") == "text"
            and str(row.get("text") or "").strip()
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


def _unique_evidence_ids(rows: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            str(row["evidence_id"]) for row in rows if row.get("evidence_id")
        )
    )
