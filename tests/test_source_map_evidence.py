from datetime import datetime, timezone

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
from medical_learning_system.source_map_evidence import (
    SourceMapEvidenceMigrationState,
    SupabaseSourceMapEvidenceCompiler,
    SupabaseSourceMapEvidenceLinkStore,
    _alignment_structure,
)
from medical_learning_system.source_registry import SourceKind, SourceRecord


SOURCE_ID = "costanzo-physiology--physical"
LOGICAL_ID = "costanzo-physiology"


def source_record(content_sha256: str, *, size_bytes=9) -> SourceRecord:
    return SourceRecord(
        source_id=SOURCE_ID,
        logical_source_id=LOGICAL_ID,
        provider="google_drive",
        provider_file_id="drive-costanzo",
        title="Costanzo Physiology.pdf",
        mime_type="application/pdf",
        size_bytes=size_bytes,
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
    assert any(link.method == AlignmentMethod.EXACT_HEADING for link in chapter_links)
    assert any(
        link.evidence_id == body.evidence_id
        and link.method == AlignmentMethod.HEADING_SEQUENCE
        for link in chapter_links
    )


def test_unmatched_heading_does_not_invent_page_range():
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

    def get_source(self, source_id):
        return self.source if source_id == self.source.source_id else None


class FakeSourceMaps:
    def __init__(self, nodes):
        self.nodes = nodes
        self.book = {
            "logical_source_id": LOGICAL_ID,
            "promoted_staging_version": 4,
            "source_map_version": 2,
        }
        self.change_on_second_read = False
        self.reads = 0

    def get_readiness(self, logical_source_id):
        return {"ready_for_hoc90": True}

    def get_logical_source(self, logical_source_id):
        self.reads += 1
        if self.change_on_second_read and self.reads > 1:
            return {
                **self.book,
                "promoted_staging_version": 5,
                "source_map_version": 3,
            }
        return dict(self.book)

    def get_source_map(self, logical_source_id):
        return [node.model_dump(mode="json") for node in self.nodes]


class FakeLinks:
    def __init__(self):
        self.committed = None

    def commit_source(self, **kwargs):
        self.committed = kwargs
        return {
            "evidence_blocks": len(kwargs["blocks"]),
            "links": len(kwargs["links"]),
            "state": kwargs["migration_state"].value,
            "staging_version": kwargs["staging_version"],
            "source_map_version": kwargs["source_map_version"],
        }


class CompilerUnderTest(SupabaseSourceMapEvidenceCompiler):
    def __init__(self, source, nodes, *, existing=0):
        self.client = object()
        self.medical = FakeMedical(source)
        self.source_maps = FakeSourceMaps(nodes)
        self.links = FakeLinks()
        self._existing = existing

    def _existing_evidence_count(self, source_id):
        return self._existing


def test_compiler_fails_before_commit_on_fingerprint_mismatch(tmp_path):
    path = tmp_path / "source.pdf"
    path.write_bytes(b"wrong bytes")
    compiler = CompilerUnderTest(
        source_record("0" * 64, size_bytes=len(b"wrong bytes")),
        map_nodes(),
    )

    with pytest.raises(RuntimeError, match="fingerprint"):
        compiler.compile_path(
            logical_source_id=LOGICAL_ID,
            source_id=SOURCE_ID,
            path=path,
        )

    assert compiler.links.committed is None


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

    assert compiler.links.committed is None


def test_compiler_commits_exact_evidence_against_immutable_stage(tmp_path, monkeypatch):
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
        bbox=(10.0, 10.0, 200.0, 30.0),
    )
    link = EvidenceStructureLink(
        evidence_id=block.evidence_id,
        source_id=SOURCE_ID,
        node_id="chapter-1",
        method=AlignmentMethod.EXACT_HEADING,
        confidence=1.0,
    )

    monkeypatch.setattr(sme, "sha256_file", lambda _: "a" * 64)
    monkeypatch.setattr(sme, "parsed_document_from_native_pdf", lambda _: sme.ParsedDocument(parser="test", blocks=[]))
    monkeypatch.setattr(sme, "materialize_evidence_only", lambda **_: [block])
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

    committed = compiler.links.committed
    assert committed is not None
    assert committed["staging_version"] == 4
    assert committed["source_map_version"] == 2
    assert committed["blocks"] == [block]
    assert committed["links"] == [link]
    assert committed["migration_state"] == SourceMapEvidenceMigrationState.COMPLETE
    assert result.linked_node_ids == ["chapter-1"]
    assert result.unlinked_node_ids == []
    assert result.staging_version == 4


def test_compiler_rechecks_promotion_before_atomic_commit(tmp_path, monkeypatch):
    path = tmp_path / "source.pdf"
    path.write_bytes(b"canonical")
    compiler = CompilerUnderTest(
        source_record("a" * 64),
        map_nodes(),
    )
    compiler.source_maps.change_on_second_read = True
    monkeypatch.setattr(sme, "sha256_file", lambda _: "a" * 64)
    monkeypatch.setattr(sme, "parsed_document_from_native_pdf", lambda _: sme.ParsedDocument(parser="test", blocks=[]))
    monkeypatch.setattr(sme, "materialize_evidence_only", lambda **_: [])
    monkeypatch.setattr(sme, "align_evidence_to_structure", lambda *_: [])

    with pytest.raises(RuntimeError, match="promotion changed"):
        compiler.compile_path(
            logical_source_id=LOGICAL_ID,
            source_id=SOURCE_ID,
            path=path,
        )

    assert compiler.links.committed is None


def test_compiler_reports_exclusion_without_committing_watermark(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "synthetic.pdf"
    with fitz.open() as doc:
        for _ in range(8):
            page = doc.new_page(width=612, height=792)
        page.insert_text((40, 100), "1 Cellular Physiology")
        page.insert_text((40, 150), "Teaching body with Smith (2020) citation.")
        page.insert_text((40, 740), "http://thepoint.lww.com")
        page.insert_text((40, 786), "booksmedicos.org")
        doc.save(path)
    compiler = CompilerUnderTest(
        source_record(sme.sha256_file(path), size_bytes=path.stat().st_size),
        map_nodes(),
    )
    result = compiler.compile_path(
        logical_source_id=LOGICAL_ID, source_id=SOURCE_ID, path=path,
    )
    committed = compiler.links.committed
    assert len(committed["blocks"]) == 3
    assert len(committed["links"]) == 6
    assert all(b.text != "booksmedicos.org" for b in committed["blocks"])
    assert len(result.excluded_blocks) == 1
    excluded = result.excluded_blocks[0]
    assert excluded["reason"] == "distributor_watermark_footer"
    assert (excluded["block_index"], excluded["page_index"], excluded["pdf_page"]) == (3, 7, 8)
    assert excluded["bbox"] and excluded["parser_version"]
    assert excluded["content_sha256"] == "5ed1562e1b8fc01563397cc666f3631632320c782073c2edb40c40fbb35dce4c"
    assert excluded["evidence_id"] not in {link.evidence_id for link in committed["links"]}
    assert "text" not in excluded and "asset_ref" not in excluded


class Response:
    def __init__(self, data):
        self.data = data


class Rpc:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return Response(
            {
                "evidence_blocks": len(self.payload["p_evidence"]),
                "links": len(self.payload["p_links"]),
                "state": self.payload["p_migration_state"],
                "staging_version": self.payload["p_staging_version"],
                "source_map_version": self.payload["p_source_map_version"],
            }
        )


class RpcClient:
    def __init__(self):
        self.calls = []

    def rpc(self, name, payload):
        self.calls.append((name, payload))
        return Rpc(payload)


def test_store_sends_atomic_payload_with_spatial_provenance():
    client = RpcClient()
    store = SupabaseSourceMapEvidenceLinkStore(client)
    source = source_record("a" * 64)
    block = make_evidence_block(
        source_id=SOURCE_ID,
        block_index=0,
        page_index=7,
        content_type=EvidenceContentType.TEXT,
        parser="test",
        parser_version="1",
        text="1 Cellular Physiology",
        bbox=(10.0, 20.0, 100.0, 40.0),
    )
    link = EvidenceStructureLink(
        evidence_id=block.evidence_id,
        source_id=SOURCE_ID,
        node_id="chapter-1",
        method=AlignmentMethod.EXACT_HEADING,
        confidence=1.0,
    )

    store.commit_source(
        logical_source_id=LOGICAL_ID,
        staging_version=4,
        source_map_version=2,
        source=source,
        blocks=[block],
        links=[link],
        migration_state=SourceMapEvidenceMigrationState.PARTIAL,
        unresolved_node_ids=["section-2"],
    )

    name, payload = client.calls[0]
    assert name == "mls_commit_source_map_evidence"
    assert payload["p_staging_version"] == 4
    assert payload["p_links"][0]["anchor_context"]["pdf_page"] == 8
    assert payload["p_links"][0]["anchor_context"]["bbox"] == [
        10.0,
        20.0,
        100.0,
        40.0,
    ]
    assert (
        payload["p_links"][0]["anchor_context"]["content_sha256"]
        == block.content_sha256
    )
