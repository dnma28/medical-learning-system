from medical_learning_system.coverage import StructureKind
from medical_learning_system.pdf_outline import (
    PdfOutlineEntry,
    structure_from_pdf_outline_entries,
)


SOURCE = "source-1"


def entries(page_shift=0):
    return [
        PdfOutlineEntry(title="1 Chapter A", depth=0, page_index=0 + page_shift),
        PdfOutlineEntry(title="Section Alpha", depth=1, page_index=1 + page_shift),
        PdfOutlineEntry(title="Subsection One", depth=2, page_index=2 + page_shift),
        PdfOutlineEntry(title="Section Beta", depth=1, page_index=5 + page_shift),
        PdfOutlineEntry(title="2 Chapter B", depth=0, page_index=10 + page_shift),
    ]


def test_outline_depth_becomes_coverage_hierarchy():
    result = structure_from_pdf_outline_entries(SOURCE, "Book", entries())
    nodes = result.nodes

    assert [node.kind for node in nodes] == [
        StructureKind.BOOK,
        StructureKind.CHAPTER,
        StructureKind.SECTION,
        StructureKind.SUBSECTION,
        StructureKind.SECTION,
        StructureKind.CHAPTER,
    ]
    assert nodes[2].parent_id == nodes[1].node_id
    assert nodes[3].parent_id == nodes[2].node_id
    assert nodes[4].parent_id == nodes[1].node_id
    assert nodes[5].parent_id == "book"


def test_outline_page_destination_becomes_one_based_pdf_page():
    result = structure_from_pdf_outline_entries(SOURCE, "Book", entries())
    assert result.nodes[1].page_start == 1
    assert result.nodes[2].page_start == 2


def test_page_movement_does_not_change_node_ids():
    first = structure_from_pdf_outline_entries(SOURCE, "Book", entries(0))
    moved = structure_from_pdf_outline_entries(SOURCE, "Book", entries(20))

    assert [node.node_id for node in first.nodes] == [
        node.node_id for node in moved.nodes
    ]


def test_duplicate_titles_under_different_parents_are_distinct():
    outline = [
        PdfOutlineEntry(title="1 Chapter A", depth=0, page_index=0),
        PdfOutlineEntry(title="Summary", depth=1, page_index=1),
        PdfOutlineEntry(title="2 Chapter B", depth=0, page_index=10),
        PdfOutlineEntry(title="Summary", depth=1, page_index=11),
    ]
    result = structure_from_pdf_outline_entries(SOURCE, "Book", outline)
    summaries = [node for node in result.nodes if node.title == "Summary"]

    assert len(summaries) == 2
    assert summaries[0].node_id != summaries[1].node_id
