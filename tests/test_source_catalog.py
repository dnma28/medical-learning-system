from datetime import datetime, timezone
from pathlib import Path

from medical_learning_system.drive_metadata import DriveFileMetadata
from medical_learning_system.source_catalog import (
    IdentityStatus,
    SourceCatalog,
    SourceMapState,
)
from medical_learning_system.source_registry import SourceKind


CATALOG = Path("data/sources/core_library.yaml")


def metadata(title: str, file_id: str = "drive-file") -> DriveFileMetadata:
    return DriveFileMetadata(
        file_id=file_id,
        title=title,
        mime_type="application/pdf",
        size_bytes=100,
        modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )


def test_costanzo_classification():
    catalog = SourceCatalog.load(CATALOG)
    result = catalog.classify(metadata("Costanzo's%20Physiology%206e (1).pdf"))
    assert result.logical_source_id == "costanzo-physiology"
    assert result.kind == SourceKind.TEXTBOOK
    assert result.edition == "6"


def test_neumann_parts_share_one_logical_source():
    catalog = SourceCatalog.load(CATALOG)
    first = catalog.classify(metadata("Kinesiology neumann (1).pdf", "n1"))
    third = catalog.classify(metadata("Kinesiology neumann (3).pdf", "n3"))

    assert first.logical_source_id == third.logical_source_id == "neumann-kinesiology"
    assert first.part_index == 1
    assert third.part_index == 3


def test_ortho_parts_map_to_magee():
    catalog = SourceCatalog.load(CATALOG)
    result = catalog.classify(metadata("Ortho 18.pdf"))
    assert result.logical_source_id == "magee-orthopedic-physical-assessment"
    assert result.part_index == 18


def test_katzung_parts_map_to_one_logical_source():
    catalog = SourceCatalog.load(CATALOG)
    first = catalog.classify(
        metadata("Katzung_1.pdf", "1QyIOGcSYdr2mJFwosd8sWH9Z9TXCSxUi")
    )
    last = catalog.classify(metadata("Katzung_20.pdf"))
    renamed = catalog.classify(
        metadata("renamed physical source.pdf", "1QyIOGcSYdr2mJFwosd8sWH9Z9TXCSxUi")
    )
    assert first.logical_source_id == last.logical_source_id == renamed.logical_source_id
    assert first.logical_source_id == "katzung-basic-clinical-pharmacology"
    assert first.part_index == 1
    assert last.part_index == 20


def test_unknown_source_is_not_dropped():
    catalog = SourceCatalog.load(CATALOG)
    result = catalog.classify(metadata("new_unknown_medical_document.pdf", "unknown-1"))
    assert result.logical_source_id.startswith("unclassified--")
    assert result.kind == SourceKind.OTHER


def test_guyton_typo_variant_is_supported():
    catalog = SourceCatalog.load(CATALOG)
    result = catalog.classify(metadata("bản dịch sách GYUTON.pdf"))
    assert result.logical_source_id == "guyton-hall-physiology"


def test_core_library_is_the_16_book_registry():
    catalog = SourceCatalog.load(CATALOG)
    assert len(catalog.sources) == 16

    moore = catalog.get("moore-clinically-oriented-anatomy")
    assert moore.identity_status == IdentityStatus.VERIFIED
    assert moore.source_map_state == SourceMapState.SECTION_ANCHORED

    medical_biochemistry = catalog.get("medical-biochemistry-183")
    assert medical_biochemistry.identity_status == IdentityStatus.POTENTIAL_DUPLICATE


def test_catalog_prefers_exact_drive_file_identity_when_available():
    catalog = SourceCatalog.model_validate(
        {
            "sources": [
                {
                    "logical_source_id": "book-a",
                    "title": "Book A",
                    "provider_file_ids": ["stable-file-id"],
                    "match_patterns": ["(?i)different title"],
                }
            ]
        }
    )
    result = catalog.classify(
        metadata("renamed source.pdf", file_id="stable-file-id")
    )
    assert result.logical_source_id == "book-a"


def test_junqueira_identity_uses_source_evidence_not_filename_year():
    catalog = SourceCatalog.load(CATALOG)
    source = catalog.get("junqueira-basic-histology")
    assert source.edition == "17"
    assert source.publication_year is None
    assert source.identity_status == IdentityStatus.VERIFIED


def test_kandel_identity_uses_registered_source_evidence():
    catalog = SourceCatalog.load(CATALOG)
    source = catalog.get("kandel-principles-neural-science")
    assert source.edition == "6"
    assert source.publication_year is None
    assert source.identity_status == IdentityStatus.VERIFIED
