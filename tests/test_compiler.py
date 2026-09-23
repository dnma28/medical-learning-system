from datetime import datetime, timezone

import pytest

from medical_learning_system.compiler import (
    CompilationAction,
    CompilationError,
    CompilationManifestStore,
    CompilationStatus,
    IncrementalSourceCompiler,
)
from medical_learning_system.coverage import (
    CoverageStore,
    StructureKind,
    StructureNode,
)
from medical_learning_system.evidence_alignment import (
    AlignmentMethod,
    EvidenceLinkStore,
    EvidenceStructureLink,
)
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    EvidenceStore,
    make_evidence_block,
)
from medical_learning_system.source_registry import (
    SourceKind,
    SourceRecord,
    SourceRegistry,
    SourceStatus,
)


def source(title="Book.pdf"):
    return SourceRecord(
        source_id="physical-1",
        logical_source_id="logical-book",
        provider="local",
        provider_file_id="physical-1",
        title=title,
        mime_type="application/pdf",
        size_bytes=10,
        modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
    )


def structure(record, path):
    return [
        StructureNode(
            source_id=record.source_id,
            node_id="book",
            kind=StructureKind.BOOK,
            title=record.title,
            depth=0,
            order_index=0,
        ),
        StructureNode(
            source_id=record.source_id,
            node_id="chapter",
            parent_id="book",
            kind=StructureKind.CHAPTER,
            title="Chapter",
            depth=1,
            order_index=1,
            page_start=1,
            page_end=1,
        ),
    ]


def evidence(record, path):
    return [
        make_evidence_block(
            source_id=record.source_id,
            block_index=0,
            page_index=0,
            content_type=EvidenceContentType.TEXT,
            parser="test",
            text="example evidence",
        )
    ]


def align(nodes, blocks):
    return [
        EvidenceStructureLink(
            evidence_id=blocks[0].evidence_id,
            source_id=blocks[0].source_id,
            node_id="chapter",
            method=AlignmentMethod.HEADING_SEQUENCE,
            confidence=0.95,
        )
    ]


def compiler(tmp_path, calls, *, fail=False):
    db = tmp_path / "compiler.sqlite3"

    def structure_loader(record, path):
        calls["structure"] += 1
        if fail:
            raise RuntimeError("parse failed")
        return structure(record, path)

    def evidence_loader(record, path):
        calls["evidence"] += 1
        return evidence(record, path)

    return IncrementalSourceCompiler(
        registry=SourceRegistry(db),
        coverage=CoverageStore(db),
        evidence=EvidenceStore(db),
        links=EvidenceLinkStore(db),
        manifests=CompilationManifestStore(db),
        structure_loader=structure_loader,
        evidence_loader=evidence_loader,
        alignment_loader=align,
        hasher=lambda path: __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
    )


def test_exact_content_is_compiled_only_once(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(b"version-one")
    calls = {"structure": 0, "evidence": 0}
    worker = compiler(tmp_path, calls)

    first = worker.compile(source(), path)
    second = worker.compile(source(title="Renamed Book.pdf"), path)

    assert first.action == CompilationAction.COMPILED
    assert second.action == CompilationAction.SKIPPED_UNCHANGED
    assert calls == {"structure": 1, "evidence": 1}
    assert second.manifest.content_sha256 == first.manifest.content_sha256


def test_changed_bytes_create_new_compilation_version(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(b"version-one")
    calls = {"structure": 0, "evidence": 0}
    worker = compiler(tmp_path, calls)

    first = worker.compile(source(), path)
    path.write_bytes(b"version-two")
    second = worker.compile(source(), path)

    assert second.action == CompilationAction.COMPILED
    assert second.manifest.content_sha256 != first.manifest.content_sha256
    assert calls == {"structure": 2, "evidence": 2}


def test_failed_compile_is_recorded_and_can_be_retried(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(b"broken-version")
    calls = {"structure": 0, "evidence": 0}
    worker = compiler(tmp_path, calls, fail=True)

    with pytest.raises(CompilationError) as raised:
        worker.compile(source(), path)

    assert raised.value.manifest.status == CompilationStatus.ERROR
    assert worker.registry.get("physical-1").status == SourceStatus.ERROR

    with pytest.raises(CompilationError):
        worker.compile(source(), path)

    assert calls["structure"] == 2


def test_success_manifest_records_grounding_and_enrichment_flag(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(b"version-one")
    calls = {"structure": 0, "evidence": 0}
    worker = compiler(tmp_path, calls)

    outcome = worker.compile(source(), path)

    assert outcome.manifest.structure_nodes == 2
    assert outcome.manifest.evidence_blocks == 1
    assert outcome.manifest.alignment_links == 1
    assert outcome.manifest.grounded_evidence_blocks == 1
    assert outcome.manifest.needs_multimodal_enrichment is True
    assert worker.registry.get("physical-1").status == SourceStatus.COMPILED
