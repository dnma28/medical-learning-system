from __future__ import annotations

from datetime import datetime
from typing import Any

from .compiler import (
    CompilationManifest,
    CompilationStatus,
    CompilationStrategy,
    IncrementalSourceCompiler,
    native_pdf_evidence_loader,
    native_pdf_structure_loader,
)
from .evidence_store import SourceEvidenceBlock
from .source_registry import (
    SourceRecord,
    SourceStatus,
    UpsertResult,
)
from .supabase_alignment import SupabaseAlignmentStore
from .supabase_storage import SupabaseMedicalStore


class SupabaseRegistryAdapter:
    def __init__(self, store: SupabaseMedicalStore):
        self.store = store

    def upsert(self, incoming: SourceRecord) -> UpsertResult:
        return self.store.upsert_source(incoming)

    def set_status(
        self,
        source_id: str,
        status: SourceStatus,
        *,
        content_sha256: str | None = None,
    ) -> SourceRecord:
        return self.store.set_source_status(
            source_id,
            status,
            content_sha256=content_sha256,
        )


class SupabaseEvidenceAdapter:
    def __init__(self, store: SupabaseMedicalStore):
        self.store = store

    def replace_source(
        self,
        source_id: str,
        blocks: list[SourceEvidenceBlock],
    ) -> None:
        self.store.replace_evidence(source_id, blocks)


class SupabaseCompilationManifestStore:
    TABLE = "mls_compilation_manifests"

    def __init__(self, client: Any):
        self.client = client

    def record(self, manifest: CompilationManifest) -> None:
        self.client.table(self.TABLE).upsert(
            _manifest_to_row(manifest),
            on_conflict="source_id,content_sha256,strategy",
        ).execute()

    def get(
        self,
        source_id: str,
        content_sha256: str,
        strategy: CompilationStrategy,
    ) -> CompilationManifest | None:
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("source_id", source_id)
            .eq("content_sha256", content_sha256)
            .eq("strategy", strategy.value)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return _manifest_from_row(rows[0]) if rows else None

    def get_success(
        self,
        source_id: str,
        content_sha256: str,
        strategy: CompilationStrategy,
    ) -> CompilationManifest | None:
        manifest = self.get(source_id, content_sha256, strategy)
        if manifest is None or manifest.status != CompilationStatus.SUCCESS:
            return None
        return manifest


def build_supabase_native_pdf_compiler(client: Any) -> IncrementalSourceCompiler:
    """Build the same native-PDF compiler against Supabase production stores."""
    medical = SupabaseMedicalStore(client)
    return IncrementalSourceCompiler(
        registry=SupabaseRegistryAdapter(medical),
        coverage=medical,
        evidence=SupabaseEvidenceAdapter(medical),
        links=SupabaseAlignmentStore(client),
        manifests=SupabaseCompilationManifestStore(client),
        structure_loader=native_pdf_structure_loader,
        evidence_loader=native_pdf_evidence_loader,
        strategy=CompilationStrategy.NATIVE_PDF,
        needs_multimodal_enrichment=True,
    )


def _manifest_to_row(manifest: CompilationManifest) -> dict[str, Any]:
    return {
        "run_id": manifest.run_id,
        "source_id": manifest.source_id,
        "content_sha256": manifest.content_sha256,
        "strategy": manifest.strategy.value,
        "status": manifest.status.value,
        "structure_nodes": manifest.structure_nodes,
        "evidence_blocks": manifest.evidence_blocks,
        "alignment_links": manifest.alignment_links,
        "grounded_evidence_blocks": manifest.grounded_evidence_blocks,
        "needs_multimodal_enrichment": manifest.needs_multimodal_enrichment,
        "error": manifest.error,
        "created_at": manifest.created_at.isoformat(),
    }


def _manifest_from_row(row: dict[str, Any]) -> CompilationManifest:
    return CompilationManifest(
        run_id=row["run_id"],
        source_id=row["source_id"],
        content_sha256=row["content_sha256"],
        strategy=CompilationStrategy(row["strategy"]),
        status=CompilationStatus(row["status"]),
        structure_nodes=row["structure_nodes"],
        evidence_blocks=row["evidence_blocks"],
        alignment_links=row["alignment_links"],
        grounded_evidence_blocks=row["grounded_evidence_blocks"],
        needs_multimodal_enrichment=bool(row["needs_multimodal_enrichment"]),
        error=row.get("error"),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])
