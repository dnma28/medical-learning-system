import pytest

from medical_learning_system.evidence_store import EvidenceContentType
from medical_learning_system.markitdown_adapter import parsed_document_from_markdown


def test_markitdown_markdown_preserves_heading_hierarchy_and_blocks():
    parsed = parsed_document_from_markdown(
        "# Chapter 1\n\nIntro paragraph.\n\n## Membrane\n\n```python\nx = 1\n```\n",
        parser_version="0.1.8",
    )

    assert parsed.parser == "markitdown"
    assert parsed.parser_version == "0.1.8"
    assert [block.heading_level for block in parsed.blocks] == [1, None, 2, None]
    assert parsed.blocks[0].text == "Chapter 1"
    assert parsed.blocks[1].text == "Intro paragraph."
    assert parsed.blocks[3].content_type == EvidenceContentType.CODE
    assert "x = 1" in parsed.blocks[3].text


def test_markitdown_blocks_use_unknown_page_zero_without_fabricating_pages():
    parsed = parsed_document_from_markdown("# Title\n\nBody")
    assert {block.page_index for block in parsed.blocks} == {0}
