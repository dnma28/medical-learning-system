import pytest

from medical_learning_system.coverage import StructureKind
from medical_learning_system.source_catalog import SourceMapState
from medical_learning_system.source_map import (
    LearningValue,
    LogicalSourceMap,
    SourceMapNode,
)


def _node(node_id, order_index, *, source_id=None, page_start=None, page_end=None):
    return SourceMapNode(
        logical_source_id="book",
        node_id=node_id,
        parent_id=None if node_id == "book" else "book",
        kind=StructureKind.BOOK if node_id == "book" else StructureKind.CHAPTER,
        title=node_id,
        depth=0 if node_id == "book" else 1,
        order_index=order_index,
        source_id=source_id,
        page_start=page_start,
        page_end=page_end,
    )


def test_logical_source_map_accepts_split_physical_sources():
    source_map = LogicalSourceMap(
        logical_source_id="magee-orthopedic-physical-assessment",
        state=SourceMapState.SECTION_ANCHORED,
        nodes=[
            SourceMapNode(
                logical_source_id="magee-orthopedic-physical-assessment",
                node_id="book",
                kind=StructureKind.BOOK,
                title="Orthopedic Physical Assessment",
                depth=0,
                order_index=0,
                learning_value=LearningValue.SUPPORTING,
            ),
            SourceMapNode(
                logical_source_id="magee-orthopedic-physical-assessment",
                node_id="chapter-6",
                parent_id="book",
                source_id="magee-part-7",
                kind=StructureKind.CHAPTER,
                title="Chapter 6",
                depth=1,
                order_index=1,
                page_start=1,
                learning_value=LearningValue.CORE_MASTERY,
            ),
            SourceMapNode(
                logical_source_id="magee-orthopedic-physical-assessment",
                node_id="chapter-7",
                parent_id="book",
                source_id="magee-part-6",
                kind=StructureKind.CHAPTER,
                title="Chapter 7",
                depth=1,
                order_index=2,
                page_start=1,
                learning_value=LearningValue.CORE_MASTERY,
            ),
        ],
    )

    assert source_map.nodes[1].source_id == "magee-part-7"
    assert source_map.nodes[2].source_id == "magee-part-6"


def test_source_map_rejects_physical_locator_without_source_id():
    with pytest.raises(ValueError, match="requires source_id"):
        SourceMapNode(
            logical_source_id="book",
            node_id="chapter",
            parent_id="book",
            kind=StructureKind.CHAPTER,
            title="Chapter",
            depth=1,
            order_index=1,
            page_start=12,
        )


@pytest.mark.parametrize(
    "locator",
    [
        {"page_start": 12},
        {"page_end": 14},
        {"source_anchor": {"parser_block": 7}},
    ],
)
def test_every_physical_locator_requires_source_id(locator):
    with pytest.raises(ValueError, match="requires source_id"):
        SourceMapNode(
            logical_source_id="book",
            node_id="section",
            parent_id="book",
            kind=StructureKind.SECTION,
            title="Section",
            depth=1,
            order_index=1,
            **locator,
        )


def test_source_map_rejects_page_end_without_page_start():
    with pytest.raises(ValueError, match="page_end requires page_start"):
        SourceMapNode(
            logical_source_id="book",
            node_id="section",
            parent_id="book",
            source_id="physical-source",
            kind=StructureKind.SECTION,
            title="Section",
            depth=1,
            order_index=1,
            page_end=14,
        )


def test_source_map_accepts_unanchored_unknown_location():
    node = SourceMapNode(
        logical_source_id="book",
        node_id="chapter",
        parent_id="book",
        kind=StructureKind.CHAPTER,
        title="Chapter",
        depth=1,
        order_index=1,
    )

    assert node.source_id is None
    assert node.page_start is None
    assert node.source_anchor == {}


def test_current_clinical_check_requires_freshness_gate():
    with pytest.raises(ValueError, match="freshness"):
        SourceMapNode(
            logical_source_id="katzung-basic-clinical-pharmacology",
            node_id="dose",
            parent_id="book",
            kind=StructureKind.SECTION,
            title="Dose",
            depth=1,
            order_index=1,
            learning_value=LearningValue.CURRENT_CLINICAL_CHECK,
            freshness_required=False,
        )


def test_source_map_rejects_missing_parent():
    with pytest.raises(ValueError, match="missing Source Map parent"):
        LogicalSourceMap(
            logical_source_id="book",
            state=SourceMapState.TOC_MAPPED,
            nodes=[
                SourceMapNode(
                    logical_source_id="book",
                    node_id="book",
                    kind=StructureKind.BOOK,
                    title="Book",
                    depth=0,
                    order_index=0,
                ),
                SourceMapNode(
                    logical_source_id="book",
                    node_id="section",
                    parent_id="missing",
                    kind=StructureKind.SECTION,
                    title="Section",
                    depth=1,
                    order_index=1,
                ),
            ],
        )


@pytest.mark.parametrize("container_kind", [StructureKind.PART, StructureKind.UNIT])
def test_source_map_preserves_part_or_unit(container_kind):
    source_map = LogicalSourceMap(
        logical_source_id="book",
        state=SourceMapState.TOC_MAPPED,
        nodes=[
            SourceMapNode(logical_source_id="book", node_id="book", kind=StructureKind.BOOK,
                          title="Book", depth=0, order_index=0),
            SourceMapNode(logical_source_id="book", node_id="container", parent_id="book",
                          kind=container_kind, title="Source container", depth=1,
                          order_index=1),
            SourceMapNode(logical_source_id="book", node_id="chapter", parent_id="container",
                          kind=StructureKind.CHAPTER, title="Chapter", depth=2, order_index=2),
            SourceMapNode(logical_source_id="book", node_id="section", parent_id="chapter",
                          kind=StructureKind.SECTION, title="Section", depth=3, order_index=3),
            SourceMapNode(logical_source_id="book", node_id="subsection", parent_id="section",
                          kind=StructureKind.SUBSECTION, title="Subsection", depth=4,
                          order_index=4),
        ],
    )
    assert source_map.nodes[1].kind == container_kind
    assert all(node.learning_value is None for node in source_map.nodes)


def test_source_map_rejects_unit_under_chapter_even_with_correct_depth():
    with pytest.raises(ValueError, match="parent kind"):
        LogicalSourceMap(
            logical_source_id="book",
            state=SourceMapState.TOC_MAPPED,
            nodes=[
                _node("book", 0),
                _node("chapter", 1),
                SourceMapNode(logical_source_id="book", node_id="unit", parent_id="chapter",
                              kind=StructureKind.UNIT, title="Unit", depth=2, order_index=2),
            ],
        )


def test_source_map_rejects_section_directly_beneath_part():
    with pytest.raises(ValueError, match="parent kind"):
        LogicalSourceMap(
            logical_source_id="book",
            state=SourceMapState.TOC_MAPPED,
            nodes=[
                _node("book", 0),
                SourceMapNode(logical_source_id="book", node_id="part", parent_id="book",
                              kind=StructureKind.PART, title="Part", depth=1, order_index=1),
                SourceMapNode(logical_source_id="book", node_id="section", parent_id="part",
                              kind=StructureKind.SECTION, title="Section", depth=2,
                              order_index=2),
            ],
        )


def test_completeness_reports_explicit_gaps_without_inference():
    source_map = LogicalSourceMap(
        logical_source_id="book",
        state=SourceMapState.SECTION_ANCHORED,
        nodes=[
            _node("book", 0),
            _node("chapter-1", 1, source_id="part-1", page_start=10, page_end=20),
            _node("chapter-2", 2),
            _node("chapter-3", 3, source_id="part-2", page_start=30),
        ],
    )

    report = source_map.completeness()

    assert report.structural_nodes == 3
    assert report.anchored_nodes == 2
    assert report.unanchored_node_ids == ["chapter-2"]
    assert report.open_ended_page_node_ids == ["chapter-3"]
    assert report.ready_for_hoc90 is False


def test_completeness_does_not_claim_readiness_from_source_ids_alone():
    source_map = LogicalSourceMap(
        logical_source_id="book",
        state=SourceMapState.SECTION_ANCHORED,
        nodes=[
            _node("book", 0),
            _node("chapter-1", 1, source_id="part-1", page_start=10, page_end=20),
            _node("chapter-2", 2, source_id="part-2", page_start=1),
        ],
    )

    assert source_map.completeness().anchored_nodes == 2
    assert source_map.completeness().ready_for_hoc90 is False
    assert "authoritative_toc_denominator_unverified" in source_map.completeness().readiness_blockers


def test_completeness_book_only_map_is_not_ready():
    source_map = LogicalSourceMap(
        logical_source_id="book",
        state=SourceMapState.TOC_MAPPED,
        nodes=[_node("book", 0)],
    )

    report = source_map.completeness()
    assert report.structural_nodes == 0
    assert report.ready_for_hoc90 is False
