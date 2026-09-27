from datetime import datetime, timezone
from hashlib import sha256

import pytest

import medical_learning_system.source_map_evidence as sme
from medical_learning_system.coverage import StructureKind
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.source_map import SourceMapNode
from medical_learning_system.source_map_evidence import (
    SourceMapEvidenceAlignment,
    SourceMapEvidenceBookState,
    SourceMapEvidenceLink,
    SourceMapEvidenceMethod,
    SourceMapEvidenceStatus,
    SupabaseSourceMapEvidenceCompiler,
)
from medical_learning_system.source_registry import SourceKind, SourceRecord


LOGICAL = "costanzo-physiology"
SOURCE = "costanzo-physical"


def source_record(payload: bytes) -> SourceRecord:
    return SourceRecord(
        source_id=SOURCE,
        logical_source_id=LOGICAL,
        provider="google_drive",
        provider_file_id="drive-1",
        title="Costanzo.pdf",
        mime_type="application/pdf",
        size_bytes=len(payload),
        modified_time=datetime(2026, 9, 27, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
        content_sha256=sha256(payload).hexdigest(),
    )


def nodes(extra_source=False):
    result = [
        SourceMapNode(
            logical_source_id=LOGICAL,
            node_id="book",
            kind=StructureKind.BOOK,
            title="Costanzo",
            depth=0,
            order_index=0,
        ),
        SourceMapNode(
            logical_source_id=LOGICAL,
            node_id="chapter",
            parent_id="book",
            source_id=SOURCE,
            kind=StructureKind.CHAPTER,
            title="1 Cellular Physiology",
            depth=1,
            order_index=1,
            page_start=1,
            source_anchor={"scope": "heading_point_not_section_range", "pdf_page": 1},
        ),
    ]
    if extra_source:
        result.append(
            SourceMapNode(
                logical_source_id=LOGICAL,
                node_id="chapter-2",
                parent_id="book",
                source_id="other-source",
                kind=StructureKind.CHAPTER,
                title="2 Other",
                depth=1,
                order_index=2,
                page_start=20,
                source_anchor={
                    "scope": "heading_point_not_section_range",
                    "pdf_page": 20,
                },
            )
        )
    return result


class FakeMedical:
    def __init__(self, source):
        self.source = source
        self.replaced = None

    def get_source(self, source_id):
        return self.source if source_id == self.source.source_id else None

    def replace_evidence(self, source_id, blocks):
        self.replaced = (source_id, blocks)


class FakeSourceMaps:
    def __init__(self, map_nodes):
        self.nodes = map_nodes
        self.calls = 0
        self.change_on_second_read = False

    def get_readiness(self, logical_source_id):
        return {"ready_for_hoc90": True}

    def get_logical_source(self, logical_source_id):
        self.calls += 1
        stage = 4 if self.change_on_second_read and self.calls > 1 else 3
        version = 2 if self.change_on_second_read and self.calls > 1 else 1
        return {
            "logical_source_id": logical_source_id,
            "promoted_staging_version": stage,
            "source_map_version": version,
        }

    def get_source_map(self, logical_source_id):
        return [item.model_dump(mode="json") for item in self.nodes]


class FakeEvidence:
    def __init__(self):
        self.statuses = []
        self.replaced = None

    def upsert_book_status(self, **kwargs):
        self.statuses.append(kwargs)

    def replace_source(self, **kwargs):
        self.replaced = kwargs
        return len(kwargs["links"])


class CompilerUnderTest(SupabaseSourceMapEvidenceCompiler):
    def __init__(self, source, map_nodes, *, existing=0):
        self.client = object()
        self.medical = FakeMedical(source)
        self.source_maps = FakeSourceMaps(map_nodes)
        self.evidence = FakeEvidence()
        self._existing = existing

    def _existing_evidence_count(self, source_id):
        return self._existing


def fake_alignment(block):
    link = SourceMapEvidenceLink(
        evidence_id=block.evidence_id,
        source_id=SOURCE,
        logical_source_id=LOGICAL,
        staging_version=3,
        node_id="chapter",
        method=SourceMapEvidenceMethod.EXACT_HEADING,
        confidence=1.0,
        status=SourceMapEvidenceStatus.PROMOTED,
        anchor_context={
            "pdf_page": 1,
            "content_sha256": block.content_sha256,
        },
        compiler_version=sme.COMPILER_VERSION,
    )
    return SourceMapEvidenceAlignment(
        links=[link],
        resolved_node_ids=["chapter"],
        unresolved_node_ids=[],
    )


def patch_parse(monkeypatch):
    block = make_evidence_block(
        source_id=SOURCE,
        block_index=0,
        page_index=0,
        content_type=EvidenceContentType.TEXT,
        parser="test",
        text="CHAPTER 1 Cellular Physiology",
    )
    monkeypatch.setattr(sme, "parsed_document_from_native_pdf", lambda _path: object())
    monkeypatch.setattr(
        sme,
        "materialize_evidence_only",
        lambda **_kwargs: [block],
    )
    monkeypatch.setattr(
        sme,
        "align_evidence_to_source_map",
        lambda **_kwargs: fake_alignment(block),
    )
    return block


def test_fingerprint_mismatch_fails_before_any_runtime_write(tmp_path):
    expected = b"canonical"
    path = tmp_path / "book.pdf"
    path.write_bytes(b"different")
    compiler = CompilerUnderTest(source_record(expected), nodes())

    with pytest.raises(RuntimeError, match="size|fingerprint"):
        compiler.compile_path(
            logical_source_id=LOGICAL,
            source_id=SOURCE,
            path=path,
        )

    assert compiler.medical.replaced is None
    assert compiler.evidence.statuses == []


def test_multi_source_book_cannot_be_marked_ready_by_one_source(tmp_path):
    payload = b"canonical"
    path = tmp_path / "book.pdf"
    path.write_bytes(payload)
    compiler = CompilerUnderTest(source_record(payload), nodes(extra_source=True))

    with pytest.raises(RuntimeError, match="multiple physical sources"):
        compiler.compile_path(
            logical_source_id=LOGICAL,
            source_id=SOURCE,
            path=path,
        )

    assert compiler.medical.replaced is None
    assert compiler.evidence.statuses == []


def test_complete_single_source_compile_moves_gate_compiling_to_ready(
    tmp_path, monkeypatch
):
    payload = b"canonical"
    path = tmp_path / "book.pdf"
    path.write_bytes(payload)
    compiler = CompilerUnderTest(source_record(payload), nodes())
    block = patch_parse(monkeypatch)

    result = compiler.compile_path(
        logical_source_id=LOGICAL,
        source_id=SOURCE,
        path=path,
    )

    assert compiler.medical.replaced == (SOURCE, [block])
    assert compiler.evidence.replaced["staging_version"] == 3
    assert [row["state"] for row in compiler.evidence.statuses] == [
        SourceMapEvidenceBookState.COMPILING,
        SourceMapEvidenceBookState.READY,
    ]
    assert result.state == SourceMapEvidenceBookState.READY
    assert result.unresolved_node_ids == []


def test_promotion_change_during_compile_fails_before_evidence_replace(
    tmp_path, monkeypatch
):
    payload = b"canonical"
    path = tmp_path / "book.pdf"
    path.write_bytes(payload)
    compiler = CompilerUnderTest(source_record(payload), nodes())
    compiler.source_maps.change_on_second_read = True
    patch_parse(monkeypatch)

    with pytest.raises(RuntimeError, match="promotion changed"):
        compiler.compile_path(
            logical_source_id=LOGICAL,
            source_id=SOURCE,
            path=path,
        )

    assert compiler.medical.replaced is None
    assert compiler.evidence.replaced is None
