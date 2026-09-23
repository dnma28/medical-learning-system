from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .coverage import (
    CoverageState,
    CoverageSummary,
    StructureKind,
    StructureNode,
    validate_structure,
)
from .evidence_store import (
    EvidenceContentType,
    EvidenceSummary,
    SourceEvidenceBlock,
)
from .source_registry import (
    SourceKind,
    SourceRecord,
    SourceStatus,
    UpsertAction,
    UpsertResult,
)


_PROCESSED = {
    SourceStatus.PARSED,
    SourceStatus.INDEXED,
    SourceStatus.GRAPHED,
    SourceStatus.COMPILED,
}


def build_supabase_client(
    *,
    url: str | None = None,
    service_role_key: str | None = None,
):
    """Build the backend-only Supabase client lazily.

    The service-role key must never be exposed to a browser, mobile client,
    repository file, or learning prompt.
    """
    resolved_url = url or os.getenv("MLS_SUPABASE_URL")
    resolved_key = service_role_key or os.getenv("MLS_SUPABASE_SERVICE_ROLE_KEY")
    if not resolved_url or not resolved_key:
        raise RuntimeError(
            "Set MLS_SUPABASE_URL and MLS_SUPABASE_SERVICE_ROLE_KEY "
            "in the backend environment."
        )

    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "Supabase support is not installed. "
            "Install with: pip install -e '.[supabase]'"
        ) from exc

    return create_client(resolved_url, resolved_key)


class SupabaseMedicalStore:
    """Cloud persistence adapter for the first Medical Learning System tables."""

    SOURCES = "mls_sources"
    STRUCTURE = "mls_structure_nodes"
    COVERAGE = "mls_coverage"
    EVIDENCE = "mls_evidence_blocks"

    def __init__(self, client: Any):
        self.client = client

    # ---- Source registry -------------------------------------------------

    def upsert_source(self, incoming: SourceRecord) -> UpsertResult:
        existing = self.get_source_by_provider(
            incoming.provider, incoming.provider_file_id
        )

        if existing is None:
            stored = incoming.model_copy(update={"status": SourceStatus.NEW})
            action = UpsertAction.CREATED
        else:
            incoming = incoming.model_copy(update={"source_id": existing.source_id})
            if existing.metadata_fingerprint() == incoming.metadata_fingerprint():
                stored = incoming.model_copy(
                    update={
                        "status": existing.status,
                        "content_sha256": existing.content_sha256,
                    }
                )
                action = UpsertAction.UNCHANGED
            else:
                next_status = (
                    SourceStatus.STALE
                    if existing.status in _PROCESSED
                    else SourceStatus.NEW
                )
                stored = incoming.model_copy(
                    update={"status": next_status, "content_sha256": None}
                )
                action = UpsertAction.CHANGED

        self.client.table(self.SOURCES).upsert(
            _source_to_row(stored),
            on_conflict="source_id",
        ).execute()
        return UpsertResult(action=action, record=stored)

    def get_source(self, source_id: str) -> SourceRecord | None:
        response = (
            self.client.table(self.SOURCES)
            .select("*")
            .eq("source_id", source_id)
            .limit(1)
            .execute()
        )
        data = _data(response)
        return _source_from_row(data[0]) if data else None

    def get_source_by_provider(
        self, provider: str, provider_file_id: str
    ) -> SourceRecord | None:
        response = (
            self.client.table(self.SOURCES)
            .select("*")
            .eq("provider", provider)
            .eq("provider_file_id", provider_file_id)
            .limit(1)
            .execute()
        )
        data = _data(response)
        return _source_from_row(data[0]) if data else None

    def set_source_status(
        self,
        source_id: str,
        status: SourceStatus,
        *,
        content_sha256: str | None = None,
    ) -> SourceRecord:
        current = self.get_source(source_id)
        if current is None:
            raise KeyError(source_id)

        updated = current.model_copy(
            update={
                "status": status,
                "content_sha256": (
                    content_sha256
                    if content_sha256 is not None
                    else current.content_sha256
                ),
            }
        )
        self.client.table(self.SOURCES).upsert(
            _source_to_row(updated),
            on_conflict="source_id",
        ).execute()
        return updated

    # ---- Coverage --------------------------------------------------------

    def replace_structure(
        self,
        source_id: str,
        nodes: list[StructureNode],
    ) -> None:
        validate_structure(source_id, nodes)
        ordered = sorted(nodes, key=lambda node: node.order_index)
        new_ids = {node.node_id for node in ordered}

        existing_response = (
            self.client.table(self.STRUCTURE)
            .select("node_id")
            .eq("source_id", source_id)
            .execute()
        )
        existing_ids = {row["node_id"] for row in _data(existing_response)}
        obsolete_ids = existing_ids - new_ids

        self.client.table(self.STRUCTURE).upsert(
            [_structure_to_row(node) for node in ordered],
            on_conflict="source_id,node_id",
        ).execute()

        coverage_seed = [
            {
                "source_id": source_id,
                "node_id": node.node_id,
                "state": CoverageState.NOT_LEARNED.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            for node in ordered
            if node.kind != StructureKind.BOOK
        ]
        if coverage_seed:
            self.client.table(self.COVERAGE).upsert(
                coverage_seed,
                on_conflict="source_id,node_id",
                ignore_duplicates=True,
            ).execute()

        for node_id in sorted(obsolete_ids):
            (
                self.client.table(self.STRUCTURE)
                .delete()
                .eq("source_id", source_id)
                .eq("node_id", node_id)
                .execute()
            )

    def get_structure(self, source_id: str) -> list[StructureNode]:
        response = (
            self.client.table(self.STRUCTURE)
            .select("*")
            .eq("source_id", source_id)
            .order("order_index")
            .execute()
        )
        return [_structure_from_row(row) for row in _data(response)]

    def set_coverage(
        self,
        source_id: str,
        node_id: str,
        state: CoverageState,
    ) -> None:
        structure_response = (
            self.client.table(self.STRUCTURE)
            .select("kind")
            .eq("source_id", source_id)
            .eq("node_id", node_id)
            .limit(1)
            .execute()
        )
        rows = _data(structure_response)
        if not rows:
            raise KeyError(node_id)
        if rows[0]["kind"] == StructureKind.BOOK.value:
            raise ValueError("book root does not have a coverage state")

        (
            self.client.table(self.COVERAGE)
            .update(
                {
                    "state": state.value,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("source_id", source_id)
            .eq("node_id", node_id)
            .execute()
        )

    def summarize_coverage(self, source_id: str) -> CoverageSummary:
        response = (
            self.client.table(self.COVERAGE)
            .select("state")
            .eq("source_id", source_id)
            .execute()
        )
        counts = Counter(row["state"] for row in _data(response))
        return CoverageSummary(
            source_id=source_id,
            total=sum(counts.values()),
            not_learned=counts[CoverageState.NOT_LEARNED.value],
            learning=counts[CoverageState.LEARNING.value],
            review=counts[CoverageState.REVIEW.value],
            mastered=counts[CoverageState.MASTERED.value],
        )

    # ---- Evidence --------------------------------------------------------

    def replace_evidence(
        self,
        source_id: str,
        blocks: list[SourceEvidenceBlock],
    ) -> None:
        if any(block.source_id != source_id for block in blocks):
            raise ValueError("all evidence blocks must belong to source_id")

        ids = [block.evidence_id for block in blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence_id")

        indexes = [block.block_index for block in blocks]
        if len(indexes) != len(set(indexes)):
            raise ValueError("duplicate block_index")

        self.client.table(self.EVIDENCE).delete().eq(
            "source_id", source_id
        ).execute()
        if blocks:
            self.client.table(self.EVIDENCE).upsert(
                [_evidence_to_row(block) for block in blocks],
                on_conflict="evidence_id",
            ).execute()

    def list_evidence(self, source_id: str) -> list[SourceEvidenceBlock]:
        response = (
            self.client.table(self.EVIDENCE)
            .select("*")
            .eq("source_id", source_id)
            .order("block_index")
            .execute()
        )
        return [_evidence_from_row(row) for row in _data(response)]

    def summarize_evidence(self, source_id: str) -> EvidenceSummary:
        blocks = self.list_evidence(source_id)
        counts = Counter(block.content_type for block in blocks)
        return EvidenceSummary(
            source_id=source_id,
            total=len(blocks),
            text=counts[EvidenceContentType.TEXT],
            image=counts[EvidenceContentType.IMAGE],
            table=counts[EvidenceContentType.TABLE],
            equation=counts[EvidenceContentType.EQUATION],
            code=counts[EvidenceContentType.CODE],
            other=counts[EvidenceContentType.OTHER],
        )


def _source_to_row(record: SourceRecord) -> dict[str, Any]:
    return {
        "source_id": record.source_id,
        "logical_source_id": record.logical_source_id,
        "provider": record.provider,
        "provider_file_id": record.provider_file_id,
        "title": record.title,
        "mime_type": record.mime_type,
        "size_bytes": record.size_bytes,
        "modified_time": record.modified_time.isoformat(),
        "kind": record.kind.value,
        "domain": record.domain,
        "edition": record.edition,
        "publication_year": record.publication_year,
        "part_index": record.part_index,
        "status": record.status.value,
        "content_sha256": record.content_sha256,
        "metadata_fingerprint": record.metadata_fingerprint(),
    }


def _source_from_row(row: dict[str, Any]) -> SourceRecord:
    return SourceRecord(
        source_id=row["source_id"],
        logical_source_id=row["logical_source_id"],
        provider=row["provider"],
        provider_file_id=row["provider_file_id"],
        title=row["title"],
        mime_type=row["mime_type"],
        size_bytes=row.get("size_bytes"),
        modified_time=datetime.fromisoformat(row["modified_time"]),
        kind=SourceKind(row["kind"]),
        domain=row.get("domain"),
        edition=row.get("edition"),
        publication_year=row.get("publication_year"),
        part_index=row.get("part_index"),
        status=SourceStatus(row["status"]),
        content_sha256=row.get("content_sha256"),
    )


def _structure_to_row(node: StructureNode) -> dict[str, Any]:
    return {
        "source_id": node.source_id,
        "node_id": node.node_id,
        "parent_id": node.parent_id,
        "kind": node.kind.value,
        "title": node.title,
        "depth": node.depth,
        "order_index": node.order_index,
        "page_start": node.page_start,
        "page_end": node.page_end,
    }


def _structure_from_row(row: dict[str, Any]) -> StructureNode:
    return StructureNode(
        source_id=row["source_id"],
        node_id=row["node_id"],
        parent_id=row.get("parent_id"),
        kind=StructureKind(row["kind"]),
        title=row["title"],
        depth=row["depth"],
        order_index=row["order_index"],
        page_start=row.get("page_start"),
        page_end=row.get("page_end"),
    )


def _evidence_to_row(block: SourceEvidenceBlock) -> dict[str, Any]:
    return {
        "evidence_id": block.evidence_id,
        "source_id": block.source_id,
        "structure_node_id": block.structure_node_id,
        "block_index": block.block_index,
        "page_index": block.page_index,
        "page_label": block.page_label,
        "content_type": block.content_type.value,
        "text": block.text,
        "asset_ref": block.asset_ref,
        "bbox": list(block.bbox) if block.bbox is not None else None,
        "parser": block.parser,
        "parser_version": block.parser_version,
        "content_sha256": block.content_sha256,
    }


def _evidence_from_row(row: dict[str, Any]) -> SourceEvidenceBlock:
    bbox = row.get("bbox")
    return SourceEvidenceBlock(
        evidence_id=row["evidence_id"],
        source_id=row["source_id"],
        structure_node_id=row.get("structure_node_id"),
        block_index=row["block_index"],
        page_index=row["page_index"],
        page_label=row.get("page_label"),
        content_type=EvidenceContentType(row["content_type"]),
        text=row.get("text"),
        asset_ref=row.get("asset_ref"),
        bbox=tuple(bbox) if bbox is not None else None,
        parser=row["parser"],
        parser_version=row.get("parser_version"),
        content_sha256=row["content_sha256"],
    )


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])
