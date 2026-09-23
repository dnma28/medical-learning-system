from datetime import datetime, timezone
from pathlib import Path

from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.knowledge_graph.source_anchor_resolution import (
    AnchorIdentityState,
    explicit_pdf_pages,
    load_legacy_source_map,
    resolve_source_anchor,
)
from medical_learning_system.source_registry import SourceKind, SourceRecord


MAP = Path("config/kg_v5_source_map.yaml")


def source(
    source_id="costanzo-physical",
    logical_source_id="costanzo-physiology",
    edition="6",
    title="anything.pdf",
):
    return SourceRecord(
        source_id=source_id,
        logical_source_id=logical_source_id,
        provider="google_drive",
        provider_file_id=source_id,
        title=title,
        mime_type="application/pdf",
        size_bytes=100,
        modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
        edition=edition,
    )


def test_verified_source_map_contains_only_explicitly_identified_ids():
    source_map = load_legacy_source_map(MAP)

    assert source_map.get("b04").logical_source_id == "guyton-hall-physiology"
    assert source_map.get("b08").logical_source_id == "costanzo-physiology"
    assert source_map.get("b06") is None


def test_unmapped_legacy_source_stays_unmapped():
    result = resolve_source_anchor(
        {
            "id": "sa-b06-homeostasis",
            "source_book_id": "b06",
            "edition": "26",
            "verification_state": "GAP",
        },
        source_map=load_legacy_source_map(MAP),
        sources=[],
    )

    assert result.identity_state == AnchorIdentityState.UNMAPPED_LEGACY_SOURCE
    assert result.evidence_candidates_resolved is False


def test_edition_mismatch_does_not_fall_back_to_wrong_book_version():
    result = resolve_source_anchor(
        {
            "source_book_id": "b08",
            "edition": "7",
            "verification_state": "PASS",
        },
        source_map=load_legacy_source_map(MAP),
        sources=[source(edition="6")],
    )

    assert result.identity_state == AnchorIdentityState.EDITION_MISMATCH
    assert result.source_id is None


def test_multiple_physical_sources_are_not_selected_by_filename():
    result = resolve_source_anchor(
        {
            "source_book_id": "b08",
            "edition": "6",
            "verification_state": "PASS",
        },
        source_map=load_legacy_source_map(MAP),
        sources=[
            source(source_id="copy-a", title="Costanzo.pdf"),
            source(source_id="copy-b", title="Costanzo copy.pdf"),
        ],
    )

    assert result.identity_state == AnchorIdentityState.AMBIGUOUS_PHYSICAL_SOURCE
    assert result.source_id is None


def test_pass_anchor_resolves_explicit_pages_to_evidence():
    physical = source()
    page_15 = make_evidence_block(
        source_id=physical.source_id,
        block_index=0,
        page_index=14,
        content_type=EvidenceContentType.TEXT,
        parser="native",
        text="Na K ATPase evidence",
    )
    page_16 = make_evidence_block(
        source_id=physical.source_id,
        block_index=1,
        page_index=15,
        content_type=EvidenceContentType.TEXT,
        parser="native",
        text="membrane potential evidence",
    )
    result = resolve_source_anchor(
        {
            "id": "sa-b08-ch1-electrophysiology",
            "source_book_id": "b08",
            "edition": "6",
            "pdf_pages": [15, 16],
            "verification_state": "PASS",
        },
        source_map=load_legacy_source_map(MAP),
        sources=[physical],
        evidence=[page_15, page_16],
    )

    assert result.identity_state == AnchorIdentityState.RESOLVED
    assert result.explicit_pdf_pages == [15, 16]
    assert result.evidence_ids == sorted(
        [page_15.evidence_id, page_16.evidence_id]
    )
    assert result.evidence_candidates_resolved is True


def test_gap_anchor_never_becomes_ready_even_when_page_exists():
    physical = source(
        source_id="guyton-physical",
        logical_source_id="guyton-hall-physiology",
        edition="15",
    )
    evidence = make_evidence_block(
        source_id=physical.source_id,
        block_index=0,
        page_index=65,
        content_type=EvidenceContentType.TEXT,
        parser="native",
        text="page 66",
    )
    result = resolve_source_anchor(
        {
            "source_book_id": "b04",
            "edition": "15",
            "pdf_start_page": 66,
            "verification_state": "GAP",
        },
        source_map=load_legacy_source_map(MAP),
        sources=[physical],
        evidence=[evidence],
    )

    assert result.identity_state == AnchorIdentityState.RESOLVED
    assert result.evidence_ids == [evidence.evidence_id]
    assert result.evidence_candidates_resolved is True
    assert result.anchor_verification_state == "GAP"


def test_page_range_is_strict_and_never_repaired():
    pages, notes = explicit_pdf_pages({"pdf_page_range": "19-27"})
    assert pages == list(range(19, 28))
    assert notes == []

    pages, notes = explicit_pdf_pages({"pdf_page_range": "27 to 19"})
    assert pages == []
    assert notes
