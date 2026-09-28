import hashlib
import json

from medical_learning_system.source_map_batch import (
    DecisionSet,
    EvidenceBlock,
    SourceIdentity,
    build_review_packet,
    evidence_pages_for_rows,
    validate_decisions,
)


def _source(binding_state="EXACT_MATCH"):
    return SourceIdentity(
        logical_source_id="neumann-kinesiology",
        source_id="neumann-part3",
        provider_file_id="drive-3",
        content_sha256="a" * 64,
        size_bytes=100,
        page_count=20,
        binding_state=binding_state,
    )


def _rows():
    return [
        {
            "node_id": "n1",
            "chapter": 12,
            "heading_expected_raw": "Hip Flexor Muscles",
            "printed_page": 518,
            "parent_id": "chapter-12",
            "kind": "subsection",
            "selected_pdf_page": 12,
        },
        {
            "node_id": "n2",
            "chapter": 12,
            "heading_expected_raw": "Primary Hip Flexors",
            "printed_page": 518,
            "parent_id": "n1",
            "kind": "subsection",
            "selected_pdf_page": 12,
        },
    ]


def _packet(binding_state="EXACT_MATCH", allowed=None):
    rows = _rows()
    blocks = [
        EvidenceBlock(
            page=12,
            block_index=4,
            text="Hip Flexor Muscles",
            bbox=(10, 10, 100, 20),
            font_sizes=[12.0],
            fonts=["Times-Bold"],
        ),
        EvidenceBlock(
            page=12,
            block_index=5,
            text="Primary Hip Flexors",
            bbox=(10, 30, 100, 40),
            font_sizes=[10.0],
            fonts=["Times-Bold"],
        ),
    ]
    return build_review_packet(
        batch_id="BATCH-12",
        manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
        rows=rows,
        source=_source(binding_state),
        blocks=blocks,
        allowed_dispositions=allowed,
    )


def test_review_packet_preserves_entire_locked_row_and_hashes_it():
    packet = _packet()
    assert packet.rows[0].locked == _rows()[0]
    serialized = json.dumps(
        packet.rows[0].locked,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert packet.rows[0].locked_sha256 == hashlib.sha256(serialized).hexdigest()
    assert packet.rows[0].evidence.best_match_text == "Hip Flexor Muscles"
    assert packet.rows[0].evidence.best_match_ratio == 1.0


def test_validate_requires_exact_row_order_and_completeness():
    packet = _packet()
    decisions = DecisionSet(
        batch_id="BATCH-12",
        decisions=[
            {"node_id": "n2", "disposition": "REVIEW_REQUIRED"},
            {"node_id": "n1", "disposition": "REVIEW_REQUIRED"},
        ],
    )
    assert any("order/set" in error for error in validate_decisions(packet, decisions))


def test_validate_rejects_page_end_for_point_locator_batch():
    packet = _packet()
    decisions = DecisionSet(
        batch_id="BATCH-12",
        decisions=[
            {"node_id": "n1", "disposition": "REVIEW_REQUIRED", "page_end": 13},
            {"node_id": "n2", "disposition": "REVIEW_REQUIRED"},
        ],
    )
    assert any("page_end must be null" in error for error in validate_decisions(packet, decisions))


def test_validate_blocks_verified_state_under_access_gap():
    packet = _packet("ACCESS_GAP_HTTP_413")
    decisions = DecisionSet(
        batch_id="BATCH-12",
        decisions=[
            {"node_id": "n1", "disposition": "VERIFIED_CANONICAL_LOCATOR"},
            {"node_id": "n2", "disposition": "ACCESS_GAP"},
        ],
    )
    errors = validate_decisions(packet, decisions)
    assert any("VERIFIED state forbidden" in error for error in errors)


def test_validate_blocks_canonical_page_label_under_access_gap():
    packet = _packet("ACCESS_GAP")
    decisions = DecisionSet(
        batch_id="BATCH-12",
        decisions=[
            {"node_id": "n1", "disposition": "ACCESS_GAP", "canonical_pdf_page": 12},
            {"node_id": "n2", "disposition": "ACCESS_GAP"},
        ],
    )
    assert any("canonical_pdf_page requires exact" in e for e in validate_decisions(packet, decisions))


def test_allowed_disposition_gate_can_force_access_gap_only():
    packet = _packet("ACCESS_GAP", allowed=["ACCESS_GAP"])
    decisions = DecisionSet(
        batch_id="BATCH-12",
        decisions=[
            {"node_id": "n1", "disposition": "REVIEW_REQUIRED"},
            {"node_id": "n2", "disposition": "ACCESS_GAP"},
        ],
    )
    assert any("is not allowed" in error for error in validate_decisions(packet, decisions))


def test_valid_access_gap_batch_passes_with_candidate_pages_only():
    packet = _packet("ACCESS_GAP", allowed=["ACCESS_GAP"])
    decisions = DecisionSet(
        batch_id="BATCH-12",
        decisions=[
            {"node_id": "n1", "disposition": "ACCESS_GAP", "candidate_pdf_page": 12},
            {"node_id": "n2", "disposition": "ACCESS_GAP", "candidate_pdf_page": 12},
        ],
    )
    assert validate_decisions(packet, decisions) == []


def test_packet_tampering_is_detected():
    packet = _packet()
    packet.rows[0].locked["heading_expected_raw"] = "Changed heading"
    decisions = DecisionSet(
        batch_id="BATCH-12",
        decisions=[
            {"node_id": "n1", "disposition": "REVIEW_REQUIRED"},
            {"node_id": "n2", "disposition": "REVIEW_REQUIRED"},
        ],
    )
    assert any("locked row hash mismatch" in error for error in validate_decisions(packet, decisions))


def test_evidence_pages_are_lazy_candidate_windows():
    rows = [
        {"node_id": "n1", "selected_pdf_page": 10},
        {"node_id": "n2", "folio_target_pages": [20, 22]},
    ]
    assert evidence_pages_for_rows(rows, neighbor_pages=1) == [
        9, 10, 11, 19, 20, 21, 22, 23
    ]


def test_candidate_page_list_is_not_silently_truncated():
    row = {"node_id": "n1", "old_candidate_pages": list(range(1, 15))}
    from medical_learning_system.source_map_batch import candidate_pages
    assert candidate_pages(row) == list(range(1, 15))


def test_evidence_page_window_clamps_at_pdf_end():
    rows = [{"node_id": "n1", "selected_pdf_page": 20}]
    assert evidence_pages_for_rows(
        rows,
        neighbor_pages=1,
        page_count=20,
    ) == [19, 20]


def test_out_of_range_candidate_page_fails_before_extraction():
    import pytest
    rows = [{"node_id": "n1", "selected_pdf_page": 21}]
    with pytest.raises(ValueError, match="candidate pages are outside"):
        evidence_pages_for_rows(rows, neighbor_pages=1, page_count=20)
