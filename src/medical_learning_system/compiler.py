from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from .coverage import CoverageStore, StructureNode
from .evidence_alignment import (
    EvidenceLinkStore,
    EvidenceStructureLink,
    align_evidence_to_structure,
)
from .evidence_store import EvidenceStore, SourceEvidenceBlock
from .native_pdf_text import parsed_document_from_native_pdf
from .parser_contract import materialize_evidence_only
from .pdf_outline import structure_from_pdf_outline
from .source_registry import (
    SourceRecord,
    SourceRegistry,
    SourceStatus,
    UpsertResult,
)
from .sources import sha256_file


class CompilationStrategy(str, Enum):
    NATIVE_PDF = "native_pdf"


class CompilationStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class CompilationAction(str, Enum):
    COMPILED = "compiled"
    SKIPPED_UNCHANGED = "skipped_unchanged"


class CompilationManifest(BaseModel):
    run_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    strategy: CompilationStrategy
    status: CompilationStatus
    structure_nodes: int = Field(ge=0)
    evidence_blocks: int = Field(ge=0)
    alignment_links: int = Field(ge=0)
    grounded_evidence_blocks: int = Field(ge=0)
    needs_multimodal_enrichment: bool
    error: str | None = None
    created_at: datetime


class CompilationOutcome(BaseModel):
    action: CompilationAction
    manifest: CompilationManifest


class CompilationError(RuntimeError):
    def __init__(self, manifest: CompilationManifest):
        self.manifest = manifest
        super().__init__(manifest.error or "source compilation failed")


class CompilationManifestStore:
    """Content-versioned history of source compilation attempts."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS compilation_manifests (
                    run_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    structure_nodes INTEGER NOT NULL,
                    evidence_blocks INTEGER NOT NULL,
                    alignment_links INTEGER NOT NULL,
                    grounded_evidence_blocks INTEGER NOT NULL,
                    needs_multimodal_enrichment INTEGER NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (source_id, content_sha256, strategy)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_compilation_source_created
                ON compilation_manifests(source_id, created_at DESC)
                """
            )

    def record(self, manifest: CompilationManifest) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO compilation_manifests (
                    run_id, source_id, content_sha256, strategy, status,
                    structure_nodes, evidence_blocks, alignment_links,
                    grounded_evidence_blocks, needs_multimodal_enrichment,
                    error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, content_sha256, strategy) DO UPDATE SET
                    run_id = excluded.run_id,
                    status = excluded.status,
                    structure_nodes = excluded.structure_nodes,
                    evidence_blocks = excluded.evidence_blocks,
                    alignment_links = excluded.alignment_links,
                    grounded_evidence_blocks = excluded.grounded_evidence_blocks,
                    needs_multimodal_enrichment =
                        excluded.needs_multimodal_enrichment,
                    error = excluded.error,
                    created_at = excluded.created_at
                """,
                (
                    manifest.run_id,
                    manifest.source_id,
                    manifest.content_sha256,
                    manifest.strategy.value,
                    manifest.status.value,
                    manifest.structure_nodes,
                    manifest.evidence_blocks,
                    manifest.alignment_links,
                    manifest.grounded_evidence_blocks,
                    int(manifest.needs_multimodal_enrichment),
                    manifest.error,
                    manifest.created_at.isoformat(),
                ),
            )

    def get(
        self,
        source_id: str,
        content_sha256: str,
        strategy: CompilationStrategy,
    ) -> CompilationManifest | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM compilation_manifests
                WHERE source_id = ?
                  AND content_sha256 = ?
                  AND strategy = ?
                """,
                (source_id, content_sha256, strategy.value),
            ).fetchone()
        return self._row(row) if row else None

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

    @staticmethod
    def _row(row: sqlite3.Row) -> CompilationManifest:
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
            needs_multimodal_enrichment=bool(
                row["needs_multimodal_enrichment"]
            ),
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class SourceRegistryBackend(Protocol):
    def upsert(self, incoming: SourceRecord) -> UpsertResult: ...

    def set_status(
        self,
        source_id: str,
        status: SourceStatus,
        *,
        content_sha256: str | None = None,
    ) -> SourceRecord: ...


class CoverageBackend(Protocol):
    def replace_structure(
        self,
        source_id: str,
        nodes: list[StructureNode],
    ) -> None: ...


class EvidenceBackend(Protocol):
    def replace_source(
        self,
        source_id: str,
        blocks: list[SourceEvidenceBlock],
    ) -> None: ...


class AlignmentBackend(Protocol):
    def replace_source(
        self,
        source_id: str,
        links: list[EvidenceStructureLink],
    ) -> None: ...


class ManifestBackend(Protocol):
    def record(self, manifest: CompilationManifest) -> None: ...

    def get_success(
        self,
        source_id: str,
        content_sha256: str,
        strategy: CompilationStrategy,
    ) -> CompilationManifest | None: ...


StructureLoader = Callable[[SourceRecord, Path], list[StructureNode]]
EvidenceLoader = Callable[[SourceRecord, Path], list[SourceEvidenceBlock]]
AlignmentLoader = Callable[
    [list[StructureNode], list[SourceEvidenceBlock]],
    list[EvidenceStructureLink],
]
Hasher = Callable[[Path], str]


class IncrementalSourceCompiler:
    """Compile one physical source once per exact byte content version."""

    def __init__(
        self,
        *,
        registry: SourceRegistryBackend,
        coverage: CoverageBackend,
        evidence: EvidenceBackend,
        links: AlignmentBackend,
        manifests: ManifestBackend,
        structure_loader: StructureLoader,
        evidence_loader: EvidenceLoader,
        alignment_loader: AlignmentLoader = align_evidence_to_structure,
        hasher: Hasher = sha256_file,
        strategy: CompilationStrategy = CompilationStrategy.NATIVE_PDF,
        needs_multimodal_enrichment: bool = True,
    ):
        self.registry = registry
        self.coverage = coverage
        self.evidence = evidence
        self.links = links
        self.manifests = manifests
        self.structure_loader = structure_loader
        self.evidence_loader = evidence_loader
        self.alignment_loader = alignment_loader
        self.hasher = hasher
        self.strategy = strategy
        self.needs_multimodal_enrichment = needs_multimodal_enrichment

    def compile(self, source: SourceRecord, path: Path) -> CompilationOutcome:
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(path)

        digest = self.hasher(path)
        registered = self.registry.upsert(source).record
        source_id = registered.source_id

        prior = self.manifests.get_success(
            source_id,
            digest,
            self.strategy,
        )
        if prior is not None:
            self.registry.set_status(
                source_id,
                SourceStatus.COMPILED,
                content_sha256=digest,
            )
            return CompilationOutcome(
                action=CompilationAction.SKIPPED_UNCHANGED,
                manifest=prior,
            )

        try:
            nodes = self.structure_loader(registered, path)
            blocks = self.evidence_loader(registered, path)
            aligned = self.alignment_loader(nodes, blocks)

            # Parsing/alignment completes before persistent source layers are
            # replaced, reducing the chance that parser failure destroys the
            # previous usable compilation.
            self.coverage.replace_structure(source_id, nodes)
            self.evidence.replace_source(source_id, blocks)
            self.links.replace_source(source_id, aligned)

            grounded = len({link.evidence_id for link in aligned})
            manifest = CompilationManifest(
                run_id=_run_id(source_id, digest, self.strategy),
                source_id=source_id,
                content_sha256=digest,
                strategy=self.strategy,
                status=CompilationStatus.SUCCESS,
                structure_nodes=len(nodes),
                evidence_blocks=len(blocks),
                alignment_links=len(aligned),
                grounded_evidence_blocks=grounded,
                needs_multimodal_enrichment=self.needs_multimodal_enrichment,
                created_at=datetime.now(timezone.utc),
            )
            self.manifests.record(manifest)
            self.registry.set_status(
                source_id,
                SourceStatus.COMPILED,
                content_sha256=digest,
            )
            return CompilationOutcome(
                action=CompilationAction.COMPILED,
                manifest=manifest,
            )
        except Exception as exc:
            manifest = CompilationManifest(
                run_id=_run_id(source_id, digest, self.strategy),
                source_id=source_id,
                content_sha256=digest,
                strategy=self.strategy,
                status=CompilationStatus.ERROR,
                structure_nodes=0,
                evidence_blocks=0,
                alignment_links=0,
                grounded_evidence_blocks=0,
                needs_multimodal_enrichment=self.needs_multimodal_enrichment,
                error=_safe_error(exc),
                created_at=datetime.now(timezone.utc),
            )
            self.manifests.record(manifest)
            self.registry.set_status(
                source_id,
                SourceStatus.ERROR,
                content_sha256=digest,
            )
            raise CompilationError(manifest) from exc


def build_native_pdf_compiler(path: Path) -> IncrementalSourceCompiler:
    """Build the low-cost native-PDF compiler on one SQLite database."""
    return IncrementalSourceCompiler(
        registry=SourceRegistry(path),
        coverage=CoverageStore(path),
        evidence=EvidenceStore(path),
        links=EvidenceLinkStore(path),
        manifests=CompilationManifestStore(path),
        structure_loader=native_pdf_structure_loader,
        evidence_loader=native_pdf_evidence_loader,
        strategy=CompilationStrategy.NATIVE_PDF,
        needs_multimodal_enrichment=True,
    )


def native_pdf_structure_loader(
    source: SourceRecord,
    path: Path,
) -> list[StructureNode]:
    return structure_from_pdf_outline(
        source.source_id,
        source.title,
        path,
    ).nodes


def native_pdf_evidence_loader(
    source: SourceRecord,
    path: Path,
) -> list[SourceEvidenceBlock]:
    parsed = parsed_document_from_native_pdf(path)
    return materialize_evidence_only(
        source_id=source.source_id,
        parsed=parsed,
    )


def _run_id(
    source_id: str,
    content_sha256: str,
    strategy: CompilationStrategy,
) -> str:
    payload = f"{source_id}|{content_sha256}|{strategy.value}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"compile-{digest}"


def _safe_error(exc: Exception) -> str:
    value = f"{exc.__class__.__name__}: {exc}".strip()
    return value[:1000]
