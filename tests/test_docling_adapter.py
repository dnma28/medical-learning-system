from dataclasses import dataclass
from enum import Enum

from medical_learning_system.docling_adapter import parsed_document_from_docling
from medical_learning_system.evidence_store import EvidenceContentType
from medical_learning_system.parser_contract import materialize_parsed_document


class Label(Enum):
    SECTION_HEADER = "section_header"
    TEXT = "text"
    TABLE = "table"
    PICTURE = "picture"


@dataclass
class BBox:
    l: float
    t: float
    r: float
    b: float


@dataclass
class Prov:
    page_no: int
    bbox: BBox


@dataclass
class Item:
    label: Label
    text: str | None = None
    level: int | None = None
    self_ref: str | None = None
    prov: list[Prov] | None = None


class Frame:
    def to_csv(self, index=False):
        assert index is False
        return "ion,value\nK,140\n"


class TableItem(Item):
    def export_to_dataframe(self, doc):
        return Frame()


class FakeDocument:
    def __init__(self, items):
        self._items = items

    def iterate_items(self):
        return iter(self._items)


def test_docling_normalizes_headings_pages_tables_and_images():
    document = FakeDocument(
        [
            (
                Item(
                    Label.SECTION_HEADER,
                    text="Chapter 1",
                    level=1,
                    self_ref="#/texts/0",
                    prov=[Prov(1, BBox(1, 2, 3, 4))],
                ),
                1,
            ),
            (
                Item(
                    Label.SECTION_HEADER,
                    text="Membrane",
                    level=2,
                    self_ref="#/texts/1",
                    prov=[Prov(5, BBox(5, 6, 7, 8))],
                ),
                2,
            ),
            (
                Item(
                    Label.TEXT,
                    text="Membrane paragraph",
                    self_ref="#/texts/2",
                    prov=[Prov(5, BBox(9, 10, 11, 12))],
                ),
                3,
            ),
            (
                TableItem(
                    Label.TABLE,
                    self_ref="#/tables/0",
                    prov=[Prov(6, BBox(13, 14, 15, 16))],
                ),
                3,
            ),
            (
                Item(
                    Label.PICTURE,
                    self_ref="#/pictures/0",
                    prov=[Prov(7, BBox(17, 18, 19, 20))],
                ),
                3,
            ),
        ]
    )

    parsed = parsed_document_from_docling(document, parser_version="2.130.0")

    assert parsed.parser == "docling"
    assert parsed.blocks[0].heading_level == 1
    assert parsed.blocks[1].page_index == 4
    assert parsed.blocks[3].content_type == EvidenceContentType.TABLE
    assert parsed.blocks[3].text.startswith("ion,value")
    assert parsed.blocks[4].content_type == EvidenceContentType.IMAGE
    assert parsed.blocks[4].asset_ref == "#/pictures/0"

    materialized = materialize_parsed_document(
        source_id="book-1",
        book_title="Book",
        parsed=parsed,
    )
    section_id = materialized.structure_nodes[2].node_id
    assert materialized.evidence_blocks[2].structure_node_id == section_id
    assert materialized.evidence_blocks[2].pdf_page == 5


def test_docling_does_not_infer_missing_heading_level():
    document = FakeDocument(
        [
            (
                Item(
                    Label.SECTION_HEADER,
                    text="Heading without level",
                    level=None,
                    self_ref="#/texts/0",
                    prov=[Prov(1, BBox(1, 2, 3, 4))],
                ),
                3,
            )
        ]
    )

    parsed = parsed_document_from_docling(document)
    assert parsed.blocks[0].heading_level is None
