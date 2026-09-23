import pytest

from medical_learning_system.coverage import StructureKind
from medical_learning_system.source_catalog import SourceMapState
from medical_learning_system.source_map import (
    LearningValue,
    LogicalSourceMap,
    SourceMapNode,
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
