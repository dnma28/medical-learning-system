from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field

from .coverage import StructureKind, StructureNode
from .drive_source import GoogleDriveSourceFetcher
from .evidence_alignment import (
    AlignmentMethod,
    EvidenceStructureLink,
    align_evidence_to_structure,
)
from .parser_contract import materialize_evidence_only
from .native_pdf_text import parsed_document_from_native_pdf
from .source_map import SourceMapNode
from .source_registry import SourceRecord
from .sources import sha256_file
from .supabase_storage import SupabaseMedicalStore


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])


class SourceMapEvidenceLink(BaseModel):
    logical_source_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_map_version: int = Field(gt=0)
    method: AlignmentMethod
    confidence: float = Field(ge=0.0, le=1.0)


class SourceMapEvidenceCompilation(BaseModel):
    logical_source_id: str
    source_id: str
    source_map_version: int
    content_sha256: str
    evidence_blocks: int = Field(ge=0)
    alignment_links: int = Field(ge=0)
    linked_node_ids: list[str] = Field(default_factory=list)
    unlinked_node_ids: list[str] = Field(default_factory=list)


class SupabaseSourceMapEvidenceLinkStore:
    TABLE = "mls_source_map_evidence_links"

    def __init__(self, client: Any):
        self.client = client

    def replace_source(
        self,
        *,
        logical_source_id: str,
        source_id: str,
        source_map_version: int,
        links: list[EvidenceStructureLink],
    ) -> None:
        if any(link.source_id != source_id for link in links):
            raise ValueError("all evidence links must belong to source_id")

        (
            self.client.table(self.TABLE)
            .delete()
            .eq("logical_source_id", logical_source_id)
            .eq("source_id", source_id)
            .execute()
        )
        if not links:
            return

        rows = [
            {
                "logical_source_id": logical_source_id,
                "node_id": link.node_id,
                "evidence_id": link.evidence_id,
                "source_id": source_id,
                "source_map_version": source_map_version,
                "method": link.method.value,
                "confidence": link.confidence,
            }
            for link in links
        ]
        self.client.table(self.TABLE).upsert(
            rows,
            on_conflict="logical_source_id,node_id,evidence_id",
        ).execute()


class SupabaseSourceMapEvidenceCompiler:
    """Compile exact PDF evidence against an already promoted Source Map.

    This component never changes Source Map nodes, learner state, curriculum, KG,
    or mastery. It verifies the registered byte fingerprint before replacing any
    evidence for a source.
    """

    SOURCE_MAP = "mls_source_map_nodes"
    EVIDENCE = "mls_evidence_blocks"

    def __init__(self, client: Any):
        self.client = client
        self.medical = SupabaseMedicalStore(client)
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

        readiness = self._readiness(logical_source_id)
        if readiness.get("ready_for_hoc90") is not True:
            raise RuntimeError("Source Map is not audited/promoted ready_for_hoc90")
        source_map_version = int(readiness.get("current_version") or 0)
        if source_map_version < 1:
            raise RuntimeError("Source Map has no promoted runtime version")

        digest = sha256_file(path)
        if digest != source.content_sha256:
            raise RuntimeError("materialized source fingerprint does not match registry")

        existing = self._existing_evidence_count(source_id)
        if existing and not allow_replace_existing:
            raise RuntimeError(
                "source already has evidence; explicit replacement authorization is required"
            )

        nodes = self._source_map_nodes(logical_source_id)
        transient = _alignment_structure(nodes, source_id=source_id)
        if len(transient) < 2:
            raise RuntimeError("promoted Source Map has no nodes for this physical source")

        parsed = parsed_document_from_native_pdf(path)
        blocks = materialize_evidence_only(source_id=source_id, parsed=parsed)
        links = align_evidence_to_structure(transient, blocks)

        # Replacing evidence first is fail-safe: any prior evidence links cascade
        # away. If the new link write fails, HỌC90 sees SOURCE_GAP rather than
        # stale context from a previous compilation.
        self.medical.replace_evidence(source_id, blocks)
        self.links.replace_source(
            logical_source_id=logical_source_id,
            source_id=source_id,
            source_map_version=source_map_version,
            links=links,
        )

        structural_ids = {
            node.node_id
            for node in transient
            if node.kind != StructureKind.BOOK
        }
        linked_ids = {
            link.node_id for link in links
            if link.node_id in structural_ids
        }
        return SourceMapEvidenceCompilation(
            logical_source_id=logical_source_id,
            source_id=source_id,
            source_map_version=source_map_version,
            content_sha256=digest,
            evidence_blocks=len(blocks),
            alignment_links=len(links),
            linked_node_ids=sorted(linked_ids),
            unlinked_node_ids=sorted(structural_ids - linked_ids),
        )

    def _readiness(self, logical_source_id: str) -> dict[str, Any]:
        response = self.client.rpc(
            "mls_source_map_readiness",
            {"p_logical_source_id": logical_source_id},
        ).execute()
        data = getattr(response, "data", None)
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        raise RuntimeError("Source Map readiness RPC returned no result")

    def _source_map_nodes(self, logical_source_id: str) -> list[SourceMapNode]:
        rows = _data(
            self.client.table(self.SOURCE_MAP)
            .select("*")
            .eq("logical_source_id", logical_source_id)
            .order("order_index")
            .execute()
        )
        if not rows:
            raise RuntimeError("promoted Source Map has no runtime nodes")
        return [SourceMapNode.model_validate(row) for row in rows]

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
        if metadata.size_bytes is not None and source.size_bytes is not None:
            if metadata.size_bytes != source.size_bytes:
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
    """Create a transient alignment tree without changing Source Map locators.

    Ancestors are retained only to preserve hierarchy. A node is alignable on
    this physical source only when its promoted Source Map binding uses source_id.
    No page_end is inferred.
    """

    by_id = {node.node_id: node for node in nodes}
    selected: set[str] = {
        node.node_id for node in nodes
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
