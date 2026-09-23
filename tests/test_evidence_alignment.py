from pathlib import Path

from medical_learning_system.coverage import StructureKind, StructureNode
from medical_learning_system.evidence_alignment import (
    AlignmentMethod,
    EvidenceLinkStore,
    align_evidence_to_structure,
)
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)


SOURCE = "book-1"


def node(node_id, title, depth, order_index, page_start, page_end, parent_id=None):
    return StructureNode(
        source_id=SOURCE,
        node_id=node_id,
        parent_id=parent_id,
        kind=(
            StructureKind.BOOK
            if depth == 0
            else StructureKind.CHAPTER
            if depth == 1
            else StructureKind.SECTION
        ),
        title=title,
        depth=depth,
        order_index=order_index,
        page_start=page_start,
        page_end=page_end,
    )


def block(index, page, text, y):
    return make_evidence_block(
        source_id=SOURCE,
        block_index=index,
        page_index=page - 1,
        content_type=EvidenceContentType.TEXT,
        parser="native",
        text=text,
        bbox=(0.0, float(y), 100.0, float(y + 10)),
    )


def test_same_page_headings_use_vertical_order():
    nodes = [
        node("book", "Book", 0, 0, None, None),
        node("ch1", "Chapter One", 1, 1, 1, 3, "book"),
        node("a", "Section A", 2, 2, 1, 1, "ch1"),
        node("b", "Section B", 2, 3, 1, 3, "ch1"),
    ]
    evidence = [
        block(0, 1, "Chapter One", 10),
        block(1, 1, "Section A", 20),
        block(2, 1, "alpha text", 30),
        block(3, 1, "Section B", 50),
        block(4, 1, "beta text", 60),
    ]

    links = align_evidence_to_structure(nodes, evidence)
    by_ev = {}
    for link in links:
        by_ev.setdefault(link.evidence_id, []).append(link)

    alpha = by_ev[evidence[2].evidence_id]
    beta = by_ev[evidence[4].evidence_id]
    assert any(link.node_id == "a" and link.method == AlignmentMethod.HEADING_SEQUENCE for link in alpha)
    assert not any(link.node_id == "b" for link in alpha)
    assert any(link.node_id == "b" and link.method == AlignmentMethod.HEADING_SEQUENCE for link in beta)


def test_nested_heading_retains_ancestor_links():
    nodes = [
        node("book", "Book", 0, 0, None, None),
        node("ch1", "Chapter One", 1, 1, 1, 3, "book"),
        node("a", "Section A", 2, 2, 1, 3, "ch1"),
    ]
    evidence = [
        block(0, 1, "Chapter One", 10),
        block(1, 1, "Section A", 20),
        block(2, 2, "body", 30),
    ]

    links = align_evidence_to_structure(nodes, evidence)
    body_nodes = {
        link.node_id
        for link in links
        if link.evidence_id == evidence[2].evidence_id
    }
    assert body_nodes == {"book", "ch1", "a"}


def test_unresolved_heading_uses_page_range_candidate_not_false_sequence():
    nodes = [
        node("book", "Book", 0, 0, None, None),
        node("ch1", "Chapter One", 1, 1, 1, 3, "book"),
        node("a", "Section A", 2, 2, 2, 3, "ch1"),
    ]
    evidence = [
        block(0, 1, "Chapter One", 10),
        block(1, 2, "body after missing heading", 30),
    ]

    links = align_evidence_to_structure(nodes, evidence)
    body = [
        link for link in links
        if link.evidence_id == evidence[1].evidence_id
    ]
    assert any(
        link.node_id == "a"
        and link.method == AlignmentMethod.PAGE_RANGE_CANDIDATE
        for link in body
    )
    assert not any(
        link.method == AlignmentMethod.HEADING_SEQUENCE
        for link in body
    )


def test_exact_heading_link_is_high_confidence():
    nodes = [
        node("book", "Book", 0, 0, None, None),
        node("ch1", "Chapter One", 1, 1, 1, 3, "book"),
    ]
    evidence = [block(0, 1, "CHAPTER ONE", 10)]

    links = align_evidence_to_structure(nodes, evidence)
    direct = next(link for link in links if link.node_id == "ch1")
    assert direct.method == AlignmentMethod.EXACT_HEADING
    assert direct.confidence == 1.0


def test_link_store_round_trip(tmp_path: Path):
    store = EvidenceLinkStore(tmp_path / "pilot.sqlite3")
    nodes = [
        node("book", "Book", 0, 0, None, None),
        node("ch1", "Chapter One", 1, 1, 1, 3, "book"),
    ]
    evidence = [
        block(0, 1, "Chapter One", 10),
        block(1, 1, "body", 20),
    ]
    links = align_evidence_to_structure(nodes, evidence)
    store.replace_source(SOURCE, links)

    found = store.list_evidence(evidence[1].evidence_id)
    assert {link.node_id for link in found} == {"book", "ch1"}
