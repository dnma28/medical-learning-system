from medical_learning_system.evidence_store import EvidenceContentType
from medical_learning_system.parser_contract import (
    from_raganything_content,
    materialize_parsed_document,
)


SOURCE = "costanzo-physiology-6e"


def test_mineru_content_materializes_structure_and_evidence():
    parsed = from_raganything_content(
        [
            {
                "type": "text",
                "text": "Chapter 1",
                "text_level": 1,
                "page_idx": 0,
                "_mineru_v2_type": "title",
                "anchor": "chapter-1",
            },
            {
                "type": "text",
                "text": "Cell membrane",
                "text_level": 2,
                "page_idx": 1,
                "_mineru_v2_type": "title",
            },
            {
                "type": "text",
                "text": "Membrane text",
                "page_idx": 1,
                "_mineru_v2_type": "paragraph",
            },
            {
                "type": "table",
                "table_body": "<table><tr><td>K+</td></tr></table>",
                "page_idx": 2,
            },
        ],
        parser_version="3.x",
    )

    materialized = materialize_parsed_document(
        source_id=SOURCE,
        book_title="Costanzo Physiology",
        parsed=parsed,
    )

    assert len(materialized.structure_nodes) == 3
    assert len(materialized.evidence_blocks) == 4
    section_id = materialized.structure_nodes[2].node_id
    assert materialized.evidence_blocks[2].structure_node_id == section_id
    assert materialized.evidence_blocks[3].content_type == EvidenceContentType.TABLE


def test_mineru_page_index_remains_zero_based():
    parsed = from_raganything_content(
        [
            {
                "type": "text",
                "text": "Chapter",
                "text_level": 1,
                "page_idx": 7,
                "_mineru_v2_type": "title",
            }
        ]
    )
    materialized = materialize_parsed_document(
        source_id=SOURCE,
        book_title="Book",
        parsed=parsed,
    )

    assert materialized.evidence_blocks[0].page_index == 7
    assert materialized.evidence_blocks[0].pdf_page == 8
