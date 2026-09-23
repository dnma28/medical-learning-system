import pytest

from medical_learning_system.coverage import StructureKind, StructureNode
from medical_learning_system.retrieval.benchmark_gold import (
    GoldResolutionError,
    SourceGroundedBenchmarkItem,
    SourceHeadingAnchor,
    resolve_source_gold,
)


PHYSICAL = "physical-source-1"
LOGICAL = "logical-book"


def structure():
    return [
        StructureNode(
            source_id=PHYSICAL,
            node_id="book",
            kind=StructureKind.BOOK,
            title="Book",
            depth=0,
            order_index=0,
        ),
        StructureNode(
            source_id=PHYSICAL,
            node_id="chapter-a",
            parent_id="book",
            kind=StructureKind.CHAPTER,
            title="Chapter A",
            depth=1,
            order_index=1,
        ),
        StructureNode(
            source_id=PHYSICAL,
            node_id="section-alpha",
            parent_id="chapter-a",
            kind=StructureKind.SECTION,
            title="Section Alpha",
            depth=2,
            order_index=2,
        ),
        StructureNode(
            source_id=PHYSICAL,
            node_id="sub-beta",
            parent_id="section-alpha",
            kind=StructureKind.SUBSECTION,
            title="Subsection Beta",
            depth=3,
            order_index=3,
        ),
    ]


def item(heading="Subsection Beta"):
    return SourceGroundedBenchmarkItem(
        query_id="q1",
        query_text="abstract query",
        language="xx",
        anchors=[
            SourceHeadingAnchor(
                logical_source_id=LOGICAL,
                chapter_title="Chapter A",
                heading_title=heading,
            )
        ],
    )


def test_resolver_finds_nested_heading_without_guessing_level():
    resolved = resolve_source_gold(
        [item()],
        logical_source_id=LOGICAL,
        physical_source_id=PHYSICAL,
        nodes=structure(),
    )

    assert resolved[0].relevant_sources == {PHYSICAL}
    assert resolved[0].relevant_structure_nodes == {"sub-beta"}


def test_normalization_handles_case_and_whitespace_only():
    candidate = item("  subsection   beta ")
    resolved = resolve_source_gold(
        [candidate],
        logical_source_id=LOGICAL,
        physical_source_id=PHYSICAL,
        nodes=structure(),
    )
    assert resolved[0].relevant_structure_nodes == {"sub-beta"}


def test_missing_heading_fails_instead_of_fuzzy_matching():
    with pytest.raises(GoldResolutionError, match="found 0"):
        resolve_source_gold(
            [item("Subsection Bet")],
            logical_source_id=LOGICAL,
            physical_source_id=PHYSICAL,
            nodes=structure(),
        )


def test_ambiguous_heading_fails():
    nodes = structure() + [
        StructureNode(
            source_id=PHYSICAL,
            node_id="sub-beta-2",
            parent_id="chapter-a",
            kind=StructureKind.SECTION,
            title="Subsection Beta",
            depth=2,
            order_index=4,
        )
    ]
    with pytest.raises(GoldResolutionError, match="found 2"):
        resolve_source_gold(
            [item()],
            logical_source_id=LOGICAL,
            physical_source_id=PHYSICAL,
            nodes=nodes,
        )


def test_logical_source_mismatch_fails():
    with pytest.raises(GoldResolutionError, match="logical source"):
        resolve_source_gold(
            [item()],
            logical_source_id="different-logical-book",
            physical_source_id=PHYSICAL,
            nodes=structure(),
        )
