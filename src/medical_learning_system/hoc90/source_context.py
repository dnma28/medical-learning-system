from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .session import SourceSpineRef


class SourceContextErrorCode(str, Enum):
    INVALID_REFERENCE = "INVALID_REFERENCE"
    SOURCE_GAP = "SOURCE_GAP"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class SourceContextUnavailable(RuntimeError):
    """Raised when an exact, source-grounded HỌC90 passage cannot be resolved."""

    def __init__(
        self,
        message: str,
        *,
        code: SourceContextErrorCode = SourceContextErrorCode.SOURCE_GAP,
    ):
        super().__init__(message)
        self.code = code


class ResolvedSourceContext(BaseModel):
    source_ref: SourceSpineRef
    evidence_ids: list[str] = Field(default_factory=list)
    passages: list[str] = Field(min_length=1)
    page_start: int | None = None
    page_end: int | None = None


def _data(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


class SupabaseHoc90SourceContextResolver:
    """Resolve exact evidence for one Source Spine node.

    Once a logical book has completed Source Map evidence migration, legacy
    fallback is permanently disabled for that book. A later Source Map promotion
    must compile a new evidence version or HỌC90 fails closed.
    """

    SOURCE_MAP_LINKS = "mls_source_map_evidence_links"
    EVIDENCE_STATUS = "mls_source_map_evidence_status"
    LOGICAL_SOURCES = "mls_logical_sources"
    SOURCE_MAP_NODES = "mls_source_map_nodes"
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
                "Source context requires both source_id and source_map_node_id.",
                code=SourceContextErrorCode.INVALID_REFERENCE,
            )

        book = self._logical_source(logical_source_id)
        current_stage = (
            int(book["promoted_staging_version"])
            if book and book.get("promoted_staging_version") is not None
            else None
        )
        if current_stage is not None:
            self._validate_current_node_affinity(
                logical_source_id=logical_source_id,
                node_id=node_id,
                source_id=source_id,
            )

        current_status = (
            self._evidence_status(logical_source_id, current_stage)
            if current_stage is not None
            else None
        )
        current_ready = (
            current_status is not None and current_status.get("state") == "ready"
        )
        ever_ready = self._has_any_ready_evidence_version(logical_source_id)

        if current_ready:
            rows = self._resolve_promoted(
                logical_source_id=logical_source_id,
                staging_version=current_stage,
                source_id=source_id,
                node_id=node_id,
            )
        elif ever_ready:
            raise SourceContextUnavailable(
                "The logical book was migrated to promoted Source Map evidence, "
                "but the current promoted Source Map version has no ready evidence "
                "migration. Legacy fallback is disabled.",
                code=SourceContextErrorCode.SOURCE_GAP,
            )
        else:
            rows = self._resolve_legacy(
                source_id=source_id,
                node_id=node_id,
            )

        text_rows = [
            row
            for row in rows
            if row.get("content_type") == "text"
            and str(row.get("text") or "").strip()
        ]
        if not text_rows:
            raise SourceContextUnavailable(
                "No exact text evidence is linked to the requested Source Map node.",
                code=SourceContextErrorCode.SOURCE_GAP,
            )

        passages = [str(row["text"]).strip() for row in text_rows]
        joined = "\n\n".join(passages)
        if len(joined) > self.max_chars:
            raise SourceContextUnavailable(
                "Resolved source context is too large for one DeepTutor interaction; "
                "use a smaller subsection/source-map node.",
                code=SourceContextErrorCode.REVIEW_REQUIRED,
            )

        evidence_ids = [
            str(row["evidence_id"]) for row in text_rows if row.get("evidence_id")
        ]
        pages = [
            int(row["page_index"])
            for row in text_rows
            if isinstance(row.get("page_index"), int)
        ]
        return ResolvedSourceContext(
            source_ref=source_ref,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            passages=passages,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
        )

    def _resolve_promoted(
        self,
        *,
        logical_source_id: str,
        staging_version: int,
        source_id: str,
        node_id: str,
    ) -> list[dict[str, Any]]:
        link_rows = _data(
            self.client.table(self.SOURCE_MAP_LINKS)
            .select("evidence_id,confidence,status")
            .eq("logical_source_id", logical_source_id)
            .eq("staging_version", staging_version)
            .eq("source_id", source_id)
            .eq("node_id", node_id)
            .eq("status", "promoted")
            .order("confidence", desc=True)
            .execute()
        )
        evidence_ids = _unique_evidence_ids(link_rows)
        if not evidence_ids:
            review_rows = _data(
                self.client.table(self.SOURCE_MAP_LINKS)
                .select("evidence_id,status")
                .eq("logical_source_id", logical_source_id)
                .eq("staging_version", staging_version)
                .eq("source_id", source_id)
                .eq("node_id", node_id)
                .eq("status", "review_required")
                .limit(1)
                .execute()
            )
            code = (
                SourceContextErrorCode.REVIEW_REQUIRED
                if review_rows
                else SourceContextErrorCode.SOURCE_GAP
            )
            raise SourceContextUnavailable(
                "No promoted evidence link exists for the requested current "
                "Source Map node; legacy fallback is disabled.",
                code=code,
            )

        return _data(
            self.client.table(self.EVIDENCE)
            .select("evidence_id,page_index,block_index,content_type,text")
            .eq("source_id", source_id)
            .in_("evidence_id", evidence_ids)
            .order("page_index")
            .order("block_index")
            .execute()
        )

    def _resolve_legacy(
        self,
        *,
        source_id: str,
        node_id: str,
    ) -> list[dict[str, Any]]:
        link_rows = _data(
            self.client.table(self.LEGACY_LINKS)
            .select("evidence_id,confidence")
            .eq("source_id", source_id)
            .eq("node_id", node_id)
            .order("confidence", desc=True)
            .execute()
        )
        evidence_ids = _unique_evidence_ids(link_rows)
        if evidence_ids:
            return _data(
                self.client.table(self.EVIDENCE)
                .select("evidence_id,page_index,block_index,content_type,text")
                .eq("source_id", source_id)
                .in_("evidence_id", evidence_ids)
                .order("page_index")
                .order("block_index")
                .execute()
            )

        # Transitional legacy scalar alignment only. Never widen by page range.
        return _data(
            self.client.table(self.EVIDENCE)
            .select("evidence_id,page_index,block_index,content_type,text")
            .eq("source_id", source_id)
            .eq("structure_node_id", node_id)
            .order("page_index")
            .order("block_index")
            .execute()
        )

    def _logical_source(self, logical_source_id: str) -> dict[str, Any] | None:
        rows = _data(
            self.client.table(self.LOGICAL_SOURCES)
            .select("logical_source_id,promoted_staging_version,source_map_version")
            .eq("logical_source_id", logical_source_id)
            .limit(1)
            .execute()
        )
        return dict(rows[0]) if rows else None

    def _evidence_status(
        self,
        logical_source_id: str,
        staging_version: int,
    ) -> dict[str, Any] | None:
        rows = _data(
            self.client.table(self.EVIDENCE_STATUS)
            .select("state,staging_version")
            .eq("logical_source_id", logical_source_id)
            .eq("staging_version", staging_version)
            .limit(1)
            .execute()
        )
        return dict(rows[0]) if rows else None

    def _has_any_ready_evidence_version(self, logical_source_id: str) -> bool:
        rows = _data(
            self.client.table(self.EVIDENCE_STATUS)
            .select("logical_source_id")
            .eq("logical_source_id", logical_source_id)
            .eq("state", "ready")
            .limit(1)
            .execute()
        )
        return bool(rows)

    def _validate_current_node_affinity(
        self,
        *,
        logical_source_id: str,
        node_id: str,
        source_id: str,
    ) -> None:
        rows = _data(
            self.client.table(self.SOURCE_MAP_NODES)
            .select("node_id,source_id")
            .eq("logical_source_id", logical_source_id)
            .eq("node_id", node_id)
            .limit(1)
            .execute()
        )
        if not rows:
            raise SourceContextUnavailable(
                "Requested Source Map node is not present in the current promoted map.",
                code=SourceContextErrorCode.SOURCE_GAP,
            )
        if rows[0].get("source_id") != source_id:
            raise SourceContextUnavailable(
                "Requested physical source does not match the current promoted "
                "Source Map node.",
                code=SourceContextErrorCode.INVALID_REFERENCE,
            )


def _unique_evidence_ids(rows: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            str(row["evidence_id"]) for row in rows if row.get("evidence_id")
        )
    )
