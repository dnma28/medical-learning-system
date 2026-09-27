from __future__ import annotations

import unicodedata
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .drive_source import GoogleDriveSourceFetcher
from .evidence_store import SourceEvidenceBlock
from .native_pdf_text import parsed_document_from_native_pdf
from .parser_contract import materialize_evidence_only
from .source_map import SourceMapNode
from .source_registry import SourceRecord
from .sources import sha256_file
from .supabase_source_map import SupabaseSourceMapStore
from .supabase_storage import SupabaseMedicalStore


COMPILER_VERSION = "source-map-native-pdf-v1"


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])


class SourceMapEvidenceMethod(str, Enum):
    EXACT_HEADING = "exact_heading"
    HEADING_PREFIX = "heading_prefix"
    HEADING_SEQUENCE = "heading_sequence"
    VERIFIED_PAGE_RANGE = "verified_page_range"
    MANUAL_CERTIFIED = "manual_certified"


class SourceMapEvidenceStatus(str, Enum):
    PROVISIONAL = "provisional"
    PROMOTED = "promoted"
    REVIEW_REQUIRED = "review_required"
    DEPRECATED = "deprecated"


class SourceMapEvidenceBookState(str, Enum):
    COMPILING = "compiling"
    REVIEW_REQUIRED = "review_required"
    READY = "ready"


class SourceMapEvidenceLink(BaseModel):
    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    logical_source_id: str = Field(min_length=1)
    staging_version: int = Field(ge=1)
    node_id: str = Field(min_length=1)
    method: SourceMapEvidenceMethod
    confidence: float = Field(ge=0.0, le=1.0)
    status: SourceMapEvidenceStatus
    anchor_context: dict[str, object] = Field(default_factory=dict)
    compiler_version: str = Field(min_length=1)


class SourceMapEvidenceAlignment(BaseModel):
    links: list[SourceMapEvidenceLink]
    resolved_node_ids: list[str]
    unresolved_node_ids: list[str]


class SourceMapEvidenceCompilation(BaseModel):
    logical_source_id: str
    source_id: str
    staging_version: int
    source_map_version: int
    content_sha256: str
    evidence_blocks: int = Field(ge=0)
    promoted_links: int = Field(ge=0)
    resolved_node_ids: list[str] = Field(default_factory=list)
    unresolved_node_ids: list[str] = Field(default_factory=list)
    state: SourceMapEvidenceBookState


class SupabaseSourceMapEvidenceStore:
    LINKS = "mls_source_map_evidence_links"
    STATUS = "mls_source_map_evidence_status"

    def __init__(self, client: Any):
        self.client = client

    def replace_source(
        self,
        *,
        logical_source_id: str,
        staging_version: int,
        source_id: str,
        links: list[SourceMapEvidenceLink],
    ) -> int:
        if any(
            link.logical_source_id != logical_source_id
            or link.staging_version != staging_version
            or link.source_id != source_id
            for link in links
        ):
            raise ValueError("Source Map evidence link identity mismatch")

        payload = [
            {
                "evidence_id": link.evidence_id,
                "node_id": link.node_id,
                "method": link.method.value,
                "confidence": link.confidence,
                "status": link.status.value,
                "anchor_context": link.anchor_context,
                "compiler_version": link.compiler_version,
            }
            for link in links
        ]
        response = self.client.rpc(
            "mls_replace_source_map_evidence_links",
            {
                "p_logical_source_id": logical_source_id,
                "p_staging_version": staging_version,
                "p_source_id": source_id,
                "p_links": payload,
            },
        ).execute()
        count = getattr(response, "data", None)
        if count != len(payload):
            raise RuntimeError("Source Map evidence link replacement readback mismatch")
        return int(count)

    def upsert_book_status(
        self,
        *,
        logical_source_id: str,
        staging_version: int,
        state: SourceMapEvidenceBookState,
        source_manifest: dict[str, object],
        evidence_blocks: int,
        promoted_links: int,
        unresolved_node_ids: list[str],
        compiler_version: str = COMPILER_VERSION,
    ) -> None:
        row = {
            "logical_source_id": logical_source_id,
            "staging_version": staging_version,
            "state": state.value,
            "compiler_version": compiler_version,
            "source_manifest": source_manifest,
            "evidence_blocks": evidence_blocks,
            "promoted_links": promoted_links,
            "unresolved_node_ids": unresolved_node_ids,
        }
        (
            self.client.table(self.STATUS)
            .upsert(
                row,
                on_conflict="logical_source_id,staging_version",
            )
            .execute()
        )

    def get_book_status(
        self,
        logical_source_id: str,
        staging_version: int,
    ) -> dict[str, Any] | None:
        response = (
            self.client.table(self.STATUS)
            .select("*")
            .eq("logical_source_id", logical_source_id)
            .eq("staging_version", staging_version)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return dict(rows[0]) if rows else None

    def has_ever_been_ready(self, logical_source_id: str) -> bool:
        response = (
            self.client.table(self.STATUS)
            .select("logical_source_id")
            .eq("logical_source_id", logical_source_id)
            .eq("state", SourceMapEvidenceBookState.READY.value)
            .limit(1)
            .execute()
        )
        return bool(_data(response))


def align_evidence_to_source_map(
    *,
    logical_source_id: str,
    staging_version: int,
    nodes: list[SourceMapNode],
    evidence: list[SourceEvidenceBlock],
    compiler_version: str = COMPILER_VERSION,
) -> SourceMapEvidenceAlignment:
    """Align evidence to certified headings without semantic/fuzzy inference."""

    if staging_version < 1:
        raise ValueError("staging_version must be positive")
    if not evidence:
        return SourceMapEvidenceAlignment(
            links=[],
            resolved_node_ids=[],
            unresolved_node_ids=[],
        )

    source_ids = {block.source_id for block in evidence}
    if len(source_ids) != 1:
        raise ValueError("one alignment run must contain one physical source")
    source_id = next(iter(source_ids))
    if any(node.logical_source_id != logical_source_id for node in nodes):
        raise ValueError("Source Map nodes do not belong to logical_source_id")

    eligible = [
        node
        for node in nodes
        if node.parent_id is not None
        and node.source_id == source_id
        and node.page_start is not None
    ]
    by_id = {node.node_id: node for node in nodes}

    blocks_by_page: dict[int, list[SourceEvidenceBlock]] = {}
    for block in evidence:
        blocks_by_page.setdefault(block.pdf_page, []).append(block)
    for blocks in blocks_by_page.values():
        blocks.sort(key=_block_position)

    anchors: dict[str, tuple[SourceEvidenceBlock, SourceMapEvidenceMethod]] = {}
    unresolved: list[SourceMapNode] = []
    for node in eligible:
        page_blocks = blocks_by_page.get(node.page_start or -1, [])
        exact = [
            block
            for block in page_blocks
            if block.text and _heading_equal(block.text, node.title)
        ]
        if len(exact) == 1:
            anchors[node.node_id] = (
                exact[0],
                SourceMapEvidenceMethod.EXACT_HEADING,
            )
            continue
        if len(exact) > 1:
            unresolved.append(node)
            continue

        prefix = [
            block
            for block in page_blocks
            if block.text and _heading_prefix(block.text, node.title)
        ]
        if len(prefix) == 1:
            anchors[node.node_id] = (
                prefix[0],
                SourceMapEvidenceMethod.HEADING_PREFIX,
            )
        else:
            unresolved.append(node)

    anchor_events = sorted(
        (
            (_block_position(block), by_id[node_id], block, method)
            for node_id, (block, method) in anchors.items()
        ),
        key=lambda item: item[0],
    )

    links: dict[tuple[str, str], SourceMapEvidenceLink] = {}
    for block in sorted(evidence, key=_block_position):
        heading_event = next(
            (
                (node, method)
                for _, node, anchor_block, method in anchor_events
                if anchor_block.evidence_id == block.evidence_id
            ),
            None,
        )
        if heading_event is not None:
            node, method = heading_event
            _add_path_links(
                links=links,
                block=block,
                node=node,
                by_id=by_id,
                logical_source_id=logical_source_id,
                staging_version=staging_version,
                method=method,
                confidence=(
                    1.0
                    if method == SourceMapEvidenceMethod.EXACT_HEADING
                    else 0.99
                ),
                compiler_version=compiler_version,
            )
            continue

        active: SourceMapNode | None = None
        position = _block_position(block)
        for event_position, node, _, _ in anchor_events:
            if event_position <= position:
                active = node
            else:
                break

        if active is not None and not _has_unresolved_barrier(
            active=active,
            block=block,
            unresolved=unresolved,
        ):
            _add_path_links(
                links=links,
                block=block,
                node=active,
                by_id=by_id,
                logical_source_id=logical_source_id,
                staging_version=staging_version,
                method=SourceMapEvidenceMethod.HEADING_SEQUENCE,
                confidence=0.95,
                compiler_version=compiler_version,
            )
            continue

        candidates = _verified_range_candidates(eligible, block.pdf_page)
        if len(candidates) == 1:
            _add_path_links(
                links=links,
                block=block,
                node=candidates[0],
                by_id=by_id,
                logical_source_id=logical_source_id,
                staging_version=staging_version,
                method=SourceMapEvidenceMethod.VERIFIED_PAGE_RANGE,
                confidence=1.0,
                compiler_version=compiler_version,
            )

    return SourceMapEvidenceAlignment(
        links=sorted(
            links.values(),
            key=lambda item: (item.evidence_id, item.node_id),
        ),
        resolved_node_ids=sorted(anchors),
        unresolved_node_ids=sorted(node.node_id for node in unresolved),
    )


class SupabaseSourceMapEvidenceCompiler:
    """Compile exact PDF evidence against the active certified Source Map."""

    def __init__(self, client: Any):
        self.client = client
        self.medical = SupabaseMedicalStore(client)
        self.source_maps = SupabaseSourceMapStore(client)
        self.evidence = SupabaseSourceMapEvidenceStore(client)

    def compile_path(
        self,
        *,
        logical_source_id: str,
        source_id: str,
        path: Path,
        allow_replace_existing: bool = False,
        require_complete_book: bool = True,
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

        nodes = [
            SourceMapNode.model_validate(row)
            for row in self.source_maps.get_source_map(logical_source_id)
        ]
        bound_sources = {
            node.source_id
            for node in nodes
            if node.parent_id is not None and node.source_id is not None
        }
        if source_id not in bound_sources:
            raise RuntimeError("physical source is not bound by the promoted Source Map")
        if require_complete_book and bound_sources != {source_id}:
            raise RuntimeError(
                "logical book spans multiple physical sources; compile all sources "
                "before setting the book evidence gate ready"
            )

        existing = self._existing_evidence_count(source_id)
        if existing and not allow_replace_existing:
            raise RuntimeError(
                "source already has evidence; explicit replacement authorization is required"
            )

        self.evidence.upsert_book_status(
            logical_source_id=logical_source_id,
            staging_version=staging_version,
            state=SourceMapEvidenceBookState.COMPILING,
            source_manifest={
                source_id: {
                    "content_sha256": digest,
                    "size_bytes": path.stat().st_size,
                }
            },
            evidence_blocks=0,
            promoted_links=0,
            unresolved_node_ids=[],
        )

        parsed = parsed_document_from_native_pdf(path)
        blocks = materialize_evidence_only(source_id=source_id, parsed=parsed)
        alignment = align_evidence_to_source_map(
            logical_source_id=logical_source_id,
            staging_version=staging_version,
            nodes=nodes,
            evidence=blocks,
        )

        eligible_ids = {
            node.node_id
            for node in nodes
            if node.parent_id is not None
            and node.source_id == source_id
            and node.page_start is not None
        }
        unresolved_ids = sorted(
            eligible_ids - set(alignment.resolved_node_ids)
        )

        # Re-read the mutable promotion pointer immediately before writes.
        current = self.source_maps.get_logical_source(logical_source_id)
        if (
            current is None
            or int(current.get("promoted_staging_version") or 0) != staging_version
            or int(current.get("source_map_version") or 0) != source_map_version
        ):
            raise RuntimeError("Source Map promotion changed during evidence compilation")

        self.medical.replace_evidence(source_id, blocks)
        promoted_links = self.evidence.replace_source(
            logical_source_id=logical_source_id,
            staging_version=staging_version,
            source_id=source_id,
            links=alignment.links,
        )

        state = (
            SourceMapEvidenceBookState.READY
            if not unresolved_ids
            else SourceMapEvidenceBookState.REVIEW_REQUIRED
        )
        self.evidence.upsert_book_status(
            logical_source_id=logical_source_id,
            staging_version=staging_version,
            state=state,
            source_manifest={
                source_id: {
                    "content_sha256": digest,
                    "size_bytes": path.stat().st_size,
                }
            },
            evidence_blocks=len(blocks),
            promoted_links=promoted_links,
            unresolved_node_ids=unresolved_ids,
        )

        return SourceMapEvidenceCompilation(
            logical_source_id=logical_source_id,
            source_id=source_id,
            staging_version=staging_version,
            source_map_version=source_map_version,
            content_sha256=digest,
            evidence_blocks=len(blocks),
            promoted_links=promoted_links,
            resolved_node_ids=alignment.resolved_node_ids,
            unresolved_node_ids=unresolved_ids,
            state=state,
        )

    def _existing_evidence_count(self, source_id: str) -> int:
        response = (
            self.client.table("mls_evidence_blocks")
            .select("evidence_id", count="exact")
            .eq("source_id", source_id)
            .limit(1)
            .execute()
        )
        count = getattr(response, "count", None)
        return int(count) if count is not None else len(_data(response))


class DriveSourceMapEvidenceCompiler:
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


def _add_path_links(
    *,
    links: dict[tuple[str, str], SourceMapEvidenceLink],
    block: SourceEvidenceBlock,
    node: SourceMapNode,
    by_id: dict[str, SourceMapNode],
    logical_source_id: str,
    staging_version: int,
    method: SourceMapEvidenceMethod,
    confidence: float,
    compiler_version: str,
) -> None:
    path: list[SourceMapNode] = []
    current: SourceMapNode | None = node
    while current is not None and current.parent_id is not None:
        if current.source_id == block.source_id:
            path.append(current)
        current = by_id.get(current.parent_id)

    for target in reversed(path):
        candidate = SourceMapEvidenceLink(
            evidence_id=block.evidence_id,
            source_id=block.source_id,
            logical_source_id=logical_source_id,
            staging_version=staging_version,
            node_id=target.node_id,
            method=method,
            confidence=confidence,
            status=SourceMapEvidenceStatus.PROMOTED,
            anchor_context={
                "pdf_page": block.pdf_page,
                "page_index": block.page_index,
                "bbox": list(block.bbox) if block.bbox is not None else None,
                "content_sha256": block.content_sha256,
                "parser": block.parser,
                "parser_version": block.parser_version,
                "matched_heading_node_id": node.node_id,
                "matched_heading_text": node.title,
            },
            compiler_version=compiler_version,
        )
        key = (candidate.evidence_id, candidate.node_id)
        current_link = links.get(key)
        if current_link is None or candidate.confidence > current_link.confidence:
            links[key] = candidate


def _verified_range_candidates(
    nodes: list[SourceMapNode],
    pdf_page: int,
) -> list[SourceMapNode]:
    candidates = [
        node
        for node in nodes
        if node.page_start is not None
        and node.page_end is not None
        and node.page_start <= pdf_page <= node.page_end
    ]
    if not candidates:
        return []
    deepest = max(node.depth for node in candidates)
    return [node for node in candidates if node.depth == deepest]


def _has_unresolved_barrier(
    *,
    active: SourceMapNode,
    block: SourceEvidenceBlock,
    unresolved: list[SourceMapNode],
) -> bool:
    return any(
        node.order_index > active.order_index
        and node.page_start is not None
        and node.page_start <= block.pdf_page
        for node in unresolved
    )


def _block_position(block: SourceEvidenceBlock) -> tuple[int, float, int]:
    y = block.bbox[1] if block.bbox is not None else float("inf")
    return (block.page_index, y, block.block_index)


def _heading_equal(block_text: str, title: str) -> bool:
    block = _norm_heading(block_text)
    target = _norm_heading(title)
    return block == target


def _heading_prefix(block_text: str, title: str) -> bool:
    block = _norm_heading(block_text)
    target = _norm_heading(title)
    return block.startswith(target + " ")


def _norm_heading(value: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if normalized.startswith("chapter "):
        normalized = normalized[len("chapter "):]
    return normalized
