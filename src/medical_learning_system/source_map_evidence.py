from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .coverage import StructureKind, StructureNode
from .drive_source import GoogleDriveSourceFetcher
from .evidence_alignment import (
    AlignmentMethod,
    EvidenceStructureLink,
    align_evidence_to_structure,
)
from .evidence_store import SourceEvidenceBlock
from .native_pdf_text import parsed_document_from_native_pdf
from .parser_contract import ParsedDocument, materialize_evidence_only
from .source_map import SourceMapNode
from .source_registry import SourceRecord
from .sources import sha256_file
from .supabase_source_map import SupabaseSourceMapStore
from .supabase_storage import SupabaseMedicalStore


COMPILER_VERSION = "source-map-evidence-v3"


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])


class SourceMapEvidenceMigrationState(str, Enum):
    PARTIAL = "partial"
    COMPLETE = "complete"
    REVIEW_REQUIRED = "review_required"
    STALE = "stale"


class SourceMapEvidenceCompilation(BaseModel):
    logical_source_id: str
    source_id: str
    staging_version: int = Field(gt=0)
    source_map_version: int = Field(gt=0)
    content_sha256: str = Field(min_length=64, max_length=64)
    evidence_blocks: int = Field(ge=0)
    alignment_links: int = Field(ge=0)
    linked_node_ids: list[str] = Field(default_factory=list)
    unlinked_node_ids: list[str] = Field(default_factory=list)
    migration_state: SourceMapEvidenceMigrationState
    excluded_blocks: list[dict[str, Any]] = Field(default_factory=list)


class SupabaseSourceMapEvidenceLinkStore:
    """Backend adapter for one atomic evidence + immutable-stage link commit."""

    TABLE = "mls_source_map_evidence_links"
    STATUS = "mls_source_map_evidence_status"

    def __init__(self, client: Any):
        self.client = client

    def commit_source(
        self,
        *,
        logical_source_id: str,
        staging_version: int,
        source_map_version: int,
        source: SourceRecord,
        blocks: list[SourceEvidenceBlock],
        links: list[EvidenceStructureLink],
        migration_state: SourceMapEvidenceMigrationState,
        unresolved_node_ids: list[str],
    ) -> dict[str, Any]:
        if source.logical_source_id != logical_source_id:
            raise ValueError("source/logical source identity mismatch")
        if not source.content_sha256:
            raise ValueError("source fingerprint is required")
        if any(block.source_id != source.source_id for block in blocks):
            raise ValueError("all evidence blocks must belong to source")
        if any(link.source_id != source.source_id for link in links):
            raise ValueError("all evidence links must belong to source")

        by_evidence = {block.evidence_id: block for block in blocks}
        if len(by_evidence) != len(blocks):
            raise ValueError("duplicate evidence_id")
        if any(link.evidence_id not in by_evidence for link in links):
            raise ValueError("link references evidence outside commit payload")

        evidence_payload = [_evidence_payload(block) for block in blocks]
        link_payload = [
            _link_payload(link, by_evidence[link.evidence_id])
            for link in links
        ]
        response = self.client.rpc(
            "mls_commit_source_map_evidence",
            {
                "p_logical_source_id": logical_source_id,
                "p_staging_version": staging_version,
                "p_source_map_version": source_map_version,
                "p_source_id": source.source_id,
                "p_expected_content_sha256": source.content_sha256,
                "p_evidence": evidence_payload,
                "p_links": link_payload,
                "p_migration_state": migration_state.value,
                "p_unresolved_node_ids": unresolved_node_ids,
                "p_compiler_version": COMPILER_VERSION,
                "p_source_manifest": {
                    source.source_id: {
                        "content_sha256": source.content_sha256,
                        "size_bytes": source.size_bytes,
                        "provider_file_id": source.provider_file_id,
                    }
                },
            },
        ).execute()
        result = getattr(response, "data", None)
        if not isinstance(result, dict):
            raise RuntimeError("atomic Source Map evidence commit returned no readback")
        if int(result.get("evidence_blocks", -1)) != len(blocks):
            raise RuntimeError("atomic evidence count readback mismatch")
        if int(result.get("links", -1)) != len(links):
            raise RuntimeError("atomic link count readback mismatch")
        if int(result.get("staging_version", -1)) != staging_version:
            raise RuntimeError("atomic staging version readback mismatch")
        return dict(result)

    def get_status(
        self,
        logical_source_id: str,
        staging_version: int,
    ) -> dict[str, Any] | None:
        rows = _data(
            self.client.table(self.STATUS)
            .select("*")
            .eq("logical_source_id", logical_source_id)
            .eq("staging_version", staging_version)
            .limit(1)
            .execute()
        )
        return dict(rows[0]) if rows else None


class SupabaseSourceMapEvidenceCompiler:
    """Compile exact PDF evidence against the active certified Source Map.

    Structural placement is deterministic publisher-structure alignment only.
    Embeddings, fuzzy matching, and model inference are not allowed here.
    """

    EVIDENCE = "mls_evidence_blocks"

    def __init__(self, client: Any):
        self.client = client
        self.medical = SupabaseMedicalStore(client)
        self.source_maps = SupabaseSourceMapStore(client)
        self.links = SupabaseSourceMapEvidenceLinkStore(client)

    def compile_path(
        self,
        *,
        logical_source_id: str,
        source_id: str,
        path: Path,
        allow_replace_existing: bool = False,
    ) -> SourceMapEvidenceCompilation:
        source = self.medical.get_source(source_id)
        if source is None:
            raise KeyError(source_id)
        if source.logical_source_id != logical_source_id:
            raise ValueError("source does not belong to logical_source_id")
        if not source.content_sha256:
            raise RuntimeError("registered source has no verified content_sha256")
        if source.size_bytes is not None and path.stat().st_size != source.size_bytes:
            raise RuntimeError("materialized source size does not match registry")

        readiness = self.source_maps.get_readiness(logical_source_id)
        if readiness.get("ready_for_hoc90") is not True:
            raise RuntimeError("Source Map is not audited/promoted ready_for_hoc90")

        book = self.source_maps.get_logical_source(logical_source_id)
        if book is None:
            raise RuntimeError("logical source registry row is missing")
        staging_version = int(book.get("promoted_staging_version") or 0)
        source_map_version = int(book.get("source_map_version") or 0)
        if staging_version < 1 or source_map_version < 1:
            raise RuntimeError("Source Map promotion metadata is incomplete")

        digest = sha256_file(path)
        if digest != source.content_sha256:
            raise RuntimeError("materialized source fingerprint does not match registry")

        existing = self._existing_evidence_count(source_id)
        if existing and not allow_replace_existing:
            raise RuntimeError(
                "source already has evidence; explicit replacement authorization is required"
            )

        nodes = [
            SourceMapNode.model_validate(row)
            for row in self.source_maps.get_source_map(logical_source_id)
        ]
        bound_sources = {
            node.source_id
            for node in nodes
            if node.kind != StructureKind.BOOK and node.source_id is not None
        }
        if source_id not in bound_sources:
            raise RuntimeError("physical source is not bound by the promoted Source Map")

        transient = _alignment_structure(nodes, source_id=source_id)
        if len(transient) < 2:
            raise RuntimeError("promoted Source Map has no alignable nodes for this source")

        parsed = parsed_document_from_native_pdf(path)
        blocks = materialize_evidence_only(source_id=source_id, parsed=parsed)
        excluded = materialize_evidence_only(
            source_id=source_id,
            parsed=ParsedDocument(
                parser=parsed.parser,
                parser_version=parsed.parser_version,
                blocks=parsed.excluded_blocks,
            ),
        )
        candidate_links = align_evidence_to_structure(transient, blocks)

        # Weak page-range candidates are useful audit signals but are not strong
        # enough to become HỌC90 exact-node provenance automatically.
        links = [
            link
            for link in candidate_links
            if link.method != AlignmentMethod.PAGE_RANGE_CANDIDATE
        ]

        structural_ids = {
            node.node_id
            for node in nodes
            if node.kind != StructureKind.BOOK
            and node.source_id == source_id
        }
        linked_ids = {
            link.node_id for link in links if link.node_id in structural_ids
        }
        unlinked_ids = sorted(structural_ids - linked_ids)
        migration_state = (
            SourceMapEvidenceMigrationState.COMPLETE
            if bound_sources == {source_id} and not unlinked_ids
            else SourceMapEvidenceMigrationState.PARTIAL
        )

        # Fast pre-flight race check. The database RPC repeats this under an
        # advisory transaction lock and is the final authority.
        current = self.source_maps.get_logical_source(logical_source_id)
        if (
            current is None
            or int(current.get("promoted_staging_version") or 0) != staging_version
            or int(current.get("source_map_version") or 0) != source_map_version
        ):
            raise RuntimeError("Source Map promotion changed during evidence compilation")

        result = self.links.commit_source(
            logical_source_id=logical_source_id,
            staging_version=staging_version,
            source_map_version=source_map_version,
            source=source,
            blocks=blocks,
            links=links,
            migration_state=migration_state,
            unresolved_node_ids=unlinked_ids,
        )

        return SourceMapEvidenceCompilation(
            logical_source_id=logical_source_id,
            source_id=source_id,
            staging_version=staging_version,
            source_map_version=source_map_version,
            content_sha256=digest,
            evidence_blocks=int(result["evidence_blocks"]),
            alignment_links=int(result["links"]),
            linked_node_ids=sorted(linked_ids),
            unlinked_node_ids=unlinked_ids,
            migration_state=migration_state,
            excluded_blocks=[
                {
                    **block.model_dump(mode="json", exclude={"text", "asset_ref"}),
                    "pdf_page": block.pdf_page,
                    "reason": raw.source_type,
                }
                for block, raw in zip(
                    excluded, sorted(parsed.excluded_blocks, key=lambda item: item.block_index)
                )
            ],
        )

    def _existing_evidence_count(self, source_id: str) -> int:
        response = (
            self.client.table(self.EVIDENCE)
            .select("evidence_id", count="exact")
            .eq("source_id", source_id)
            .limit(1)
            .execute()
        )
        count = getattr(response, "count", None)
        if count is not None:
            return int(count)
        return len(_data(response))


class DriveSourceMapEvidenceCompiler:
    """Materialize one registered Drive PDF privately, then compile it."""

    def __init__(
        self,
        *,
        compiler: SupabaseSourceMapEvidenceCompiler,
        fetcher: GoogleDriveSourceFetcher,
    ):
        self.compiler = compiler
        self.fetcher = fetcher

    def compile_source(
        self,
        *,
        logical_source_id: str,
        source: SourceRecord,
        allow_replace_existing: bool = False,
    ) -> SourceMapEvidenceCompilation:
        if source.provider != "google_drive":
            raise ValueError("source provider must be google_drive")
        metadata = self.fetcher.get_metadata(source.provider_file_id)
        if (
            metadata.size_bytes is not None
            and source.size_bytes is not None
            and metadata.size_bytes != source.size_bytes
        ):
            raise RuntimeError("Drive source size changed from registered source")

        with self.fetcher.materialize_pdf(source.provider_file_id) as path:
            return self.compiler.compile_path(
                logical_source_id=logical_source_id,
                source_id=source.source_id,
                path=path,
                allow_replace_existing=allow_replace_existing,
            )


def _alignment_structure(
    nodes: list[SourceMapNode],
    *,
    source_id: str,
) -> list[StructureNode]:
    """Create a transient alignment tree without inventing any locator."""

    by_id = {node.node_id: node for node in nodes}
    selected: set[str] = {
        node.node_id
        for node in nodes
        if node.source_id == source_id or node.kind == StructureKind.BOOK
    }

    for node in list(nodes):
        if node.node_id not in selected:
            continue
        parent_id = node.parent_id
        while parent_id is not None:
            selected.add(parent_id)
            parent = by_id.get(parent_id)
            parent_id = parent.parent_id if parent is not None else None

    transient: list[StructureNode] = []
    for node in nodes:
        if node.node_id not in selected:
            continue
        page_start = None
        if node.source_id == source_id:
            page_start = node.page_start
            if page_start is None:
                raw = node.source_anchor.get("pdf_page")
                if isinstance(raw, int) and raw > 0:
                    page_start = raw

        transient.append(
            StructureNode(
                source_id=source_id,
                node_id=node.node_id,
                parent_id=node.parent_id,
                kind=node.kind,
                title=node.title,
                depth=node.depth,
                order_index=node.order_index,
                page_start=page_start,
                page_end=node.page_end if node.source_id == source_id else None,
            )
        )
    return transient


def _evidence_payload(block: SourceEvidenceBlock) -> dict[str, Any]:
    return {
        "evidence_id": block.evidence_id,
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


def _link_payload(
    link: EvidenceStructureLink,
    block: SourceEvidenceBlock,
) -> dict[str, Any]:
    return {
        "node_id": link.node_id,
        "evidence_id": link.evidence_id,
        "method": link.method.value,
        "confidence": link.confidence,
        "anchor_context": {
            "pdf_page": block.pdf_page,
            "page_index": block.page_index,
            "bbox": list(block.bbox) if block.bbox is not None else None,
            "content_sha256": block.content_sha256,
            "parser": block.parser,
            "parser_version": block.parser_version,
        },
    }
