from medical_learning_system.evidence_store import EvidenceContentType
from medical_learning_system.parser_contract import ParsedBlock, ParsedDocument, materialize_evidence_only


def test_evidence_only_materialization_preserves_pages_and_bbox():
    parsed = ParsedDocument(
        parser="native-test",
        parser_version="1",
        blocks=[
            ParsedBlock(
                block_index=0,
                page_index=7,
                content_type=EvidenceContentType.TEXT,
                text="alpha",
                bbox=(1.0, 2.0, 3.0, 4.0),
                source_type="native_pdf_text",
            )
        ],
    )

    evidence = materialize_evidence_only(source_id="source-1", parsed=parsed)

    assert len(evidence) == 1
    assert evidence[0].page_index == 7
    assert evidence[0].pdf_page == 8
    assert evidence[0].bbox == (1.0, 2.0, 3.0, 4.0)
    assert evidence[0].structure_node_id is None
