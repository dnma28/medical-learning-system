import pytest

from medical_learning_system.coverage import CoverageStore, StructureKind
from medical_learning_system.structure_extraction import (
    StructureExtractionError,
    structure_from_raganything_content,
)


SOURCE = "costanzo-physiology-6e"


def content(page_shift: int = 0):
    return [
        {
            "type": "text",
            "text": "Chapter One",
            "text_level": 1,
            "page_idx": 0 + page_shift,
            "_mineru_v2_type": "title",
        },
        {
            "type": "text",
            "text": "Membranes",
            "text_level": 3,
            "page_idx": 2 + page_shift,
            "_mineru_v2_type": "title",
        },
        {
            "type": "text",
            "text": "Transport",
            "text_level": 3,
            "page_idx": 5 + page_shift,
            "_mineru_v2_type": "title",
        },
        {
            "type": "text",
            "text": "Chapter Two",
            "text_level": 1,
            "page_idx": 20 + page_shift,
            "_mineru_v2_type": "title",
        },
    ]


def test_skipped_raw_heading_levels_are_normalized_into_tree_depth():
    result = structure_from_raganything_content(
        SOURCE, "Costanzo Physiology", content()
    )
    nodes = result.nodes

    assert [node.kind for node in nodes] == [
        StructureKind.BOOK,
        StructureKind.CHAPTER,
        StructureKind.SECTION,
        StructureKind.SECTION,
        StructureKind.CHAPTER,
    ]
    assert nodes[2].parent_id == nodes[1].node_id
    assert nodes[3].parent_id == nodes[1].node_id
    assert nodes[4].parent_id == "book"


def test_parser_page_index_becomes_one_based_page_start():
    result = structure_from_raganything_content(
        SOURCE, "Costanzo Physiology", content()
    )
    assert result.nodes[1].page_start == 1
    assert result.nodes[2].page_start == 3


def test_page_changes_do_not_change_structure_node_ids():
    first = structure_from_raganything_content(
        SOURCE, "Costanzo Physiology", content(page_shift=0)
    )
    moved = structure_from_raganything_content(
        SOURCE, "Costanzo Physiology", content(page_shift=10)
    )

    assert [node.node_id for node in first.nodes] == [
        node.node_id for node in moved.nodes
    ]


def test_same_heading_under_different_parents_gets_different_ids():
    blocks = [
        {"type": "text", "text": "Chapter A", "text_level": 1, "page_idx": 0},
        {"type": "text", "text": "Summary", "text_level": 2, "page_idx": 1},
        {"type": "text", "text": "Chapter B", "text_level": 1, "page_idx": 10},
        {"type": "text", "text": "Summary", "text_level": 2, "page_idx": 11},
    ]
    result = structure_from_raganything_content(SOURCE, "Book", blocks)
    summaries = [node for node in result.nodes if node.title == "Summary"]
    assert len(summaries) == 2
    assert summaries[0].node_id != summaries[1].node_id


def test_unleveled_title_is_flagged_and_not_guessed():
    blocks = [
        {
            "type": "text",
            "text": "Unleveled title",
            "_mineru_v2_type": "title",
            "page_idx": 0,
        }
    ]
    with pytest.raises(StructureExtractionError, match="no usable heading"):
        structure_from_raganything_content(SOURCE, "Book", blocks)


def test_extracted_structure_can_be_stored_by_coverage_engine(tmp_path):
    result = structure_from_raganything_content(
        SOURCE, "Costanzo Physiology", content()
    )
    store = CoverageStore(tmp_path / "coverage.sqlite3")
    store.replace_structure(SOURCE, result.nodes)

    assert store.summarize(SOURCE).total == 4
