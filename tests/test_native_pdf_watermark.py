"""No source PDF/text fixtures: synthetic CI and opt-in canonical PDF61 QA."""

import os
from pathlib import Path

import pytest

from medical_learning_system.compiler import native_pdf_evidence_loader
from medical_learning_system.coverage import StructureKind, StructureNode
from medical_learning_system.evidence_alignment import align_evidence_to_structure
from medical_learning_system.native_pdf_text import parsed_document_from_native_pdf
from medical_learning_system.parser_contract import materialize_evidence_only
from medical_learning_system.sources import sha256_file


def test_footer_disposition_preserves_urls_citations_and_block_indexes(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "synthetic.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        for y, text in [
            (80, "Teaching heading"),
            (130, "booksmedicos.org"),
            (180, "See Smith (2020), p. 7."),
            (740, "http://thepoint.lww.com"),
            (786, "booksmedicos.org"),
        ]:
            page.insert_text((40, y), text)
        doc.save(path)
    parsed = parsed_document_from_native_pdf(path)
    blocks = materialize_evidence_only(source_id="synthetic", parsed=parsed)
    assert [b.block_index for b in blocks] == [0, 1, 2, 3]
    assert [b.text for b in blocks] == [
        "Teaching heading",
        "booksmedicos.org",
        "See Smith (2020), p. 7.",
        "http://thepoint.lww.com",
    ]
    assert [b.block_index for b in parsed.excluded_blocks] == [4]
    assert parsed.excluded_blocks[0].source_type == "distributor_watermark_footer"
    # Incremental compiler shares the native parser/materializer boundary.
    assert (
        native_pdf_evidence_loader(
            type("Source", (), {"source_id": "synthetic"})(), path
        )
        == blocks
    )


def test_bates_pdf61_real_source():
    path_value = os.environ.get("MLS_BATES_PDF")
    if not path_value:
        pytest.skip("MLS_BATES_PDF must point to the private canonical Bates PDF")
    path = Path(path_value)
    assert path.stat().st_size == 33876839
    assert (
        sha256_file(path)
        == "c949dc8e55fc4a6a930e0deb5a8ebeb34ea3bdc202da3de352ec1338aaf51169"
    )
    source_id = "bates-physical-examination--d2a8614d9b39"
    parsed = parsed_document_from_native_pdf(path, start_page=61, end_page=61)
    blocks = materialize_evidence_only(source_id=source_id, parsed=parsed)
    assert len(blocks) == 9
    assert [b.block_index for b in blocks] == list(range(9))
    assert "http://thepoint.lww.com" in blocks[4].text
    # Published v1 content hashes: every legitimate block including citation
    # and attribution must survive byte normalization unchanged.
    assert [b.content_sha256 for b in blocks] == [
        "7835b1d30add071420b7072ff2807373920cf72f1c22b7a048ad587749b18f9c",
        "63ef82522b1a6ac45f262168c20a1f75a14f1ec25ba2816c7c8d149d140c22d9",
        "2cc1d9e997a477ea677975ee2a2fb872076de6b3f5b37af75a226645bbbf72f5",
        "a72183876def4dfba88e1d0445fa0c2841677ef09c46d1e477ebd2e93a9d85b5",
        "7d39c83cbdeee49bfbfda5df5b3d24862092918897aa122f8a7113522754560a",
        "90ad0690a34430874cfb5ae5319c0760d773b3f4b4f9e940527166f0c4ac4011",
        "976e08c43d1922106f1cc41e01027bb0186e6b7e09a50793eaeebef1692223b3",
        "898901f6a3fb64234b5c1cf0b7682ea773d2ffd045e729a751e8332b5a3b870c",
        "72c59dc98f6b034cc155bfb3fc00ac5416b9071d7c64694204452e53cbcdde6e",
    ]
    assert len(parsed.excluded_blocks) == 1
    excluded = parsed.excluded_blocks[0]
    assert (excluded.block_index, excluded.page_index) == (9, 60)
    assert excluded.source_type == "distributor_watermark_footer"
    assert excluded.bbox == pytest.approx((273.612, 761.85754, 346.638, 774.14252))
    # Frozen ancestry topology; title point comes from the native outline,
    # independently of the extracted body block used by alignment.
    import fitz

    with fitz.open(path) as doc:
        outline = doc.get_toc()
    structure = [
        StructureNode(
            source_id=source_id,
            node_id="book",
            kind=StructureKind.BOOK,
            title="Bates",
            depth=0,
            order_index=0,
        )
    ]
    for index, kind in [
        (10, StructureKind.UNIT),
        (11, StructureKind.CHAPTER),
        (12, StructureKind.SECTION),
    ]:
        structure.append(
            StructureNode(
                source_id=source_id,
                node_id=str(index),
                parent_id=structure[-1].node_id,
                kind=kind,
                title=outline[index][1],
                depth=len(structure),
                order_index=index,
                page_start=outline[index][2],
            )
        )
    links = align_evidence_to_structure(structure, blocks)
    assert len(links) == 8
    assert {link.evidence_id for link in links} == {
        blocks[7].evidence_id,
        blocks[8].evidence_id,
    }
    assert all(link.confidence >= 0.95 for link in links)


@pytest.mark.parametrize(
    "text",
    [
        "http://thepoint.lww.com",
        "https://booksmedicos.org/reference",
        "Smith (2020), p. 7.",
        "See booksmedicos.org for details.",
    ],
)
def test_legitimate_footer_text_is_retained(tmp_path, text):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "footer.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.insert_text((40, 786), text)
        doc.save(path)
    parsed = parsed_document_from_native_pdf(path)
    assert [b.text for b in parsed.blocks] == [text]
    assert parsed.excluded_blocks == []
