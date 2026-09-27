from datetime import datetime, timezone
from pathlib import Path

import pytest

import medical_learning_system.source_map_evidence as sme
from medical_learning_system.coverage import StructureKind
from medical_learning_system.evidence_alignment import (
    AlignmentMethod,
    EvidenceStructureLink,
    align_evidence_to_structure,
)
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.source_map import SourceMapNode
from medical_learning_system.source_registry import SourceKind, SourceRecord
from medical_learning_system.source_map_evidence import (
    SupabaseSourceMapEvidenceCompiler,
    _alignment_structure,
)


SOURCE_ID = "costanzo-physiology--physical"
LOGICAL_ID = "costanzo-physiology"


def source_record(content_sha256: str) -> SourceRecord:
    return SourceRecord(
        source_id=SOURCE_ID,
        logical_source_id=LOGICAL_ID,
        provider="google_drive",
        provider_file_id="drive-costanzo",
        title="Costanzo Physiology.pdf",
        mime_type="application/pdf",
        size_bytes=9,
        modified_time=datetime(2026, 9, 27, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
        content_sha256=content_sha256,
    )


def map_nodes(title: str = "1 Cellular Physiology") -> list[SourceMapNode]:
    return [
        SourceMapNode(
            logical_source_id=LOGICAL_ID,
            node_id="book",
            kind=StructureKind.BOOK,
            title="Costanzo Physiology",
            depth=0,
            order_index=0,
        ),
        SourceMapNode(
            logical_source_id=LOGICAL_ID,
            node_id="chapter-1",
            parent_id="book",
            source_id=SOURCE_ID,
            kind=StructureKind.CHAPTER,
            title=title,
            depth=1,
            order_index=1,
            page_start=8,
            source_anchor={
                "pdf_page": 8,
                "scope": "heading_point_not_section_range",
            },
        ),
    ]


def test_alignment_uses_promoted_heading_point_without_inferred_page_end():
    structure = _alignment_structure(map_nodes(), source_id=SOURCE_ID)
    assert structure[1].page_start == 8
    assert structure[1].page_end is None

    heading = make_evidence_block(
        source_id=SOURCE_ID,
        block_index=0,
        page_index=7,
        content_type=EvidenceContentType.TEXT,
        parser="test",
        text="1 Cellular Physiology",
        bbox=(10.0, 10.0, 200.0, 30.0),
    )
    body = make_evidence_block(
        source_id=SOURCE_ID,
        block_index=1,
        page_index=7,
        content_type=EvidenceContentType.TEXT,
        parser="test",
        text="Body fluid physiology begins here.",
        bbox=(10.0, 40.0, 200.0, 80.0),
    )

    links = align_evidence_to_structure(structure, [heading, body])

    chapter_links = [link for link in links if link.node_id == "chapter-1"]
    assert any(
        link.method == AlignmentMethod.EXACT_HEADING
        for link in chapter_links
    )
    assert any(
        link.evidence_id == body.evidence_id
        and link.method == AlignmentMethod.HEADING_SEQUENCE
        for link in chapter_links
    )


def test_unmatched_heading_does_not_invent_page_range_candidate():
    structure = _alignment_structure(
        map_nodes(title="Heading not present"),
        source_id=SOURCE_ID,
    )
    body = make_evidence_block(
        source_id=SOURCE_ID,
        block_index=0,
        page_index=7,
        content_type=EvidenceContentType.TEXT,
        parser="test",
        text="Unrelated page text.",
    )

    links = align_evidence_to_structure(structure, [body])

    assert not any(link.node_id == "chapter-1" for link in links)


class FakeMedical:
    def __init__(self, source):
        self.source = source
        self.replaced = None

    def get_source(self, source_id):
        return self.source if source_id == self.source.source_id else None

    def replace_evidence(self, source_id, blocks):
        self.replaced = (source_id, blocks)


class FakeLinks:
    def __init__(self):
        self.replaced = None

    def replace_source(self, **kwargs):
        self.replaced = kwargs


class CompilerUnderTest(SupabaseSourceMapEvidenceCompiler):
    def __init__(self, source, nodes, *, existing=0):
        self.client = object()
        self.medical = FakeMedical(source)
        self.links = FakeLinks()
        self._nodes = nodes
        self._existing = existing

    def _readiness(self, logical_source_id):
        return {"ready_for_hoc90": True, "current_version": 2}

    def _source_map_nodes(self, logical_source_id):
        return self._nodes

    def _existing_evidence_count(self, source_id):
        return self._existing


def test_compiler_fails_before_writes_on_fingerprint_mismatch(tmp_path):
    path = tmp_path / "source.pdf"
    path.write_bytes(b"wrong bytes")
    compiler = CompilerUnderTest(
        source_record("0" * 64),
        map_nodes(),
    )

    with pytest.raises(RuntimeError, match="fingerprint"):
        compiler.compile_path(
            logical_source_id=LOGICAL_ID,
            source_id=SOURCE_ID,
            path=path,
        )

    assert compiler.medical.replaced is None
    assert compiler.links.replaced is None


def test_compiler_requires_explicit_replacement_authorization(tmp_path, monkeypatch):
    path = tmp_path / "source.pdf"
    path.write_bytes(b"canonical")
    compiler = CompilerUnderTest(
        source_record("a" * 64),
        map_nodes(),
        existing=1,
    )
    monkeypatch.setattr(sme, "sha256_file", lambda _: "a" * 64)

    with pytest.raises(RuntimeError, match="replacement authorization"):
        compiler.compile_path(
            logical_source_id=LOGICAL_ID,
            source_id=SOURCE_ID,
            path=path,
        )

    assert compiler.medical.replaced is None


def test_compiler_persists_evidence_and_promoted_map_links(tmp_path, monkeypatch):
    path = tmp_path / "source.pdf"
    path.write_bytes(b"canonical")
    compiler = CompilerUnderTest(
        source_record("a" * 64),
        map_nodes(),
    )
    block = make_evidence_block(
        source_id=SOURCE_ID,
        block_index=0,
        page_index=7,
        content_type=EvidenceContentType.TEXT,
        parser="test",
        text="1 Cellular Physiology",
    )
    link = EvidenceStructureLink(
        evidence_id=block.evidence_id,
        source_id=SOURCE_ID,
        node_id="chapter-1",
        method=AlignmentMethod.EXACT_HEADING,
        confidence=1.0,
    )

    monkeypatch.setattr(sme, "sha256_file", lambda _: "a" * 64)
    monkeypatch.setattr(
        sme,
        "parsed_document_from_native_pdf",
        lambda _: object(),
    )
    monkeypatch.setattr(
        sme,
        "materialize_evidence_only",
        lambda **_: [block],
    )
    monkeypatch.setattr(
        sme,
        "align_evidence_to_structure",
        lambda _nodes, _blocks: [link],
    )

    result = compiler.compile_path(
        logical_source_id=LOGICAL_ID,
        source_id=SOURCE_ID,
        path=path,
    )

    assert compiler.medical.replaced == (SOURCE_ID, [block])
    assert compiler.links.replaced["logical_source_id"] == LOGICAL_ID
    assert compiler.links.replaced["source_map_version"] == 2
    assert compiler.links.replaced["links"] == [link]
    assert result.linked_node_ids == ["chapter-1"]
    assert result.unlinked_node_ids == []
