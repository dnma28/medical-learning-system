from medical_learning_system.coverage import StructureKind
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.source_map import SourceMapNode
from medical_learning_system.source_map_evidence import (
    SourceMapEvidenceMethod,
    SourceMapEvidenceStatus,
    SupabaseSourceMapEvidenceStore,
    align_evidence_to_source_map,
)


def node(
    node_id,
    title,
    *,
    parent_id,
    depth,
    order_index,
    page_start=None,
    page_end=None,
    source_id="physical-1",
    kind=StructureKind.SUBSECTION,
):
    return SourceMapNode(
        logical_source_id="book-1",
        node_id=node_id,
        parent_id=parent_id,
        kind=kind,
        title=title,
        depth=depth,
        order_index=order_index,
        source_id=source_id,
        page_start=page_start,
        page_end=page_end,
        source_anchor=(
            {"scope": "heading_point_not_section_range", "pdf_page": page_start}
            if page_start is not None
            else {}
        ),
    )


def block(index, page_index, text, *, bbox=(10.0, 20.0, 100.0, 40.0)):
    return make_evidence_block(
        source_id="physical-1",
        block_index=index,
        page_index=page_index,
        content_type=EvidenceContentType.TEXT,
        parser="pymupdf-native",
        parser_version="1",
        text=text,
        bbox=bbox,
    )


def source_map():
    return [
        SourceMapNode(
            logical_source_id="book-1",
            node_id="book",
            parent_id=None,
            kind=StructureKind.BOOK,
            title="Book",
            depth=0,
            order_index=0,
        ),
        node(
            "chapter",
            "1 Cellular Physiology",
            parent_id="book",
            depth=1,
            order_index=1,
            page_start=1,
            kind=StructureKind.CHAPTER,
        ),
        node(
            "section",
            "Resting Membrane Potential",
            parent_id="chapter",
            depth=2,
            order_index=2,
            page_start=2,
            kind=StructureKind.SECTION,
        ),
    ]


def test_exact_headings_and_sequence_create_promoted_links():
    evidence = [
        block(0, 0, "CHAPTER 1 Cellular Physiology"),
        block(1, 0, "chapter introduction"),
        block(2, 1, "RESTING MEMBRANE POTENTIAL"),
        block(3, 1, "resting membrane paragraph"),
    ]

    result = align_evidence_to_source_map(
        logical_source_id="book-1",
        staging_version=3,
        nodes=source_map(),
        evidence=evidence,
    )

    assert set(result.resolved_node_ids) == {"chapter", "section"}
    assert result.unresolved_node_ids == []
    section_links = [link for link in result.links if link.node_id == "section"]
    assert section_links
    assert all(link.status == SourceMapEvidenceStatus.PROMOTED for link in section_links)
    assert {link.method for link in section_links} == {
        SourceMapEvidenceMethod.EXACT_HEADING,
        SourceMapEvidenceMethod.HEADING_SEQUENCE,
    }
    paragraph = next(
        link
        for link in section_links
        if link.evidence_id == evidence[3].evidence_id
    )
    assert paragraph.anchor_context["pdf_page"] == 2
    assert paragraph.anchor_context["content_sha256"] == evidence[3].content_sha256


def test_unresolved_heading_is_a_barrier_not_silent_parent_leakage():
    evidence = [
        block(0, 0, "CHAPTER 1 Cellular Physiology"),
        block(1, 0, "chapter introduction"),
        block(2, 1, "a paragraph where a section heading should have been found"),
    ]

    result = align_evidence_to_source_map(
        logical_source_id="book-1",
        staging_version=3,
        nodes=source_map(),
        evidence=evidence,
    )

    assert result.resolved_node_ids == ["chapter"]
    assert result.unresolved_node_ids == ["section"]
    paragraph_links = [
        link for link in result.links if link.evidence_id == evidence[2].evidence_id
    ]
    assert paragraph_links == []


def test_verified_range_can_link_without_inventing_page_end():
    nodes = source_map()
    nodes[2] = nodes[2].model_copy(
        update={
            "page_start": 2,
            "page_end": 3,
            "source_anchor": {"scope": "verified_section_range", "pdf_page": 2},
        }
    )
    evidence = [
        block(0, 0, "CHAPTER 1 Cellular Physiology"),
        block(1, 1, "body text without a captured section heading"),
    ]

    result = align_evidence_to_source_map(
        logical_source_id="book-1",
        staging_version=3,
        nodes=nodes,
        evidence=evidence,
    )

    range_link = next(
        link
        for link in result.links
        if link.evidence_id == evidence[1].evidence_id
        and link.node_id == "section"
    )
    assert range_link.method == SourceMapEvidenceMethod.VERIFIED_PAGE_RANGE
    assert range_link.confidence == 1.0
    assert "section" in result.unresolved_node_ids


def test_other_physical_source_nodes_are_not_alignment_targets():
    nodes = source_map()
    nodes.append(
        node(
            "other-source-section",
            "Foreign section",
            parent_id="chapter",
            depth=2,
            order_index=3,
            page_start=2,
            source_id="physical-2",
            kind=StructureKind.SECTION,
        )
    )
    result = align_evidence_to_source_map(
        logical_source_id="book-1",
        staging_version=3,
        nodes=nodes,
        evidence=[block(0, 0, "CHAPTER 1 Cellular Physiology")],
    )
    assert not any(
        link.node_id == "other-source-section" for link in result.links
    )


class Response:
    def __init__(self, data):
        self.data = data


class Rpc:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return Response(len(self.payload["p_links"]))


class Client:
    def __init__(self):
        self.calls = []

    def rpc(self, name, payload):
        self.calls.append((name, payload))
        return Rpc(payload)


def test_store_uses_atomic_replace_rpc_and_preserves_version_identity():
    client = Client()
    store = SupabaseSourceMapEvidenceStore(client)
    evidence = [block(0, 0, "CHAPTER 1 Cellular Physiology")]
    alignment = align_evidence_to_source_map(
        logical_source_id="book-1",
        staging_version=3,
        nodes=source_map(),
        evidence=evidence,
    )

    count = store.replace_source(
        logical_source_id="book-1",
        staging_version=3,
        source_id="physical-1",
        links=alignment.links,
    )

    assert count == len(alignment.links)
    name, payload = client.calls[0]
    assert name == "mls_replace_source_map_evidence_links"
    assert payload["p_staging_version"] == 3
    assert payload["p_source_id"] == "physical-1"
