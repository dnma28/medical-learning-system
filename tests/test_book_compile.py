from medical_learning_system.book_compile import build_compile_report
from medical_learning_system.source_map_batch import (
    BatchScope,
    EvidenceBlock,
    ReviewPacket,
    ReviewPacketRow,
    RowEvidence,
    SourceIdentity,
    canonical_sha256,
)


def _source(binding_state="EXACT_MATCH"):
    return SourceIdentity(
        logical_source_id="guyton-hall-physiology",
        source_id="guyton-source",
        provider_file_id="drive-guyton",
        content_sha256="a" * 64,
        size_bytes=100,
        page_count=1100,
        binding_state=binding_state,
    )


def _scope(classification_required=True):
    return BatchScope(
        work_key="source-map:guyton-hall-physiology:compile-pilot",
        unit_field="chapter",
        authorized_units=[31],
        expected_counts={"31": 1},
        expected_total=1,
        pdf_page_start=421,
        pdf_page_end=438,
        reverse_coverage_required=True,
        classification_required=classification_required,
    )


def _row(*, reasons=None, locked=None):
    locked = locked or {
        "node_id": "n1",
        "chapter": 31,
        "final_classification": "REQUIRED_SECTION",
        "review_status": "PASS",
        "selected_pdf_page": 426,
    }
    return ReviewPacketRow(
        node_id="n1",
        locked=locked,
        locked_sha256=canonical_sha256(locked),
        evidence=RowEvidence(
            candidate_pages=[426],
            best_match_page=426,
            best_match_block_index=9,
            best_match_text="Synthetic heading",
            best_match_ratio=1.0,
            surrounding_blocks=[
                EvidenceBlock(
                    page=426,
                    block_index=9,
                    text="Synthetic heading",
                    bbox=(1, 1, 10, 10),
                )
            ],
            visual_required_reasons=reasons or [],
        ),
    )


def _packet(*, row=None, binding_state="EXACT_MATCH", classification_required=True):
    scope = _scope(classification_required=classification_required)
    source = _source(binding_state)
    packet = ReviewPacket(
        batch_id="GUYTON-COMPILE-PILOT",
        work_key=scope.work_key,
        manifest_sha256="b" * 64,
        scope_sha256=canonical_sha256(scope.model_dump(mode="json")),
        scope_evidence_sha256="c" * 64,
        scope=scope,
        source=source,
        evidence_pages=[426],
        scope_blocks=[],
        rows=[row or _row()],
    )
    return packet


def test_compile_report_routes_clean_source_backed_row_to_independent_review():
    report = build_compile_report(_packet())
    assert report.total_rows == 1
    assert report.evidence_matched_rows == 1
    assert report.evidence_exception_rows == 0
    assert report.structural_review_rows == 0
    assert report.review_exception_rows == 0
    assert report.next_gate == "INDEPENDENT_REVIEW"
    assert report.publish_authorized is False


def test_compile_report_keeps_low_match_in_finite_exception_queue():
    report = build_compile_report(
        _packet(row=_row(reasons=["LOW_TEXT_MATCH"]))
    )
    assert report.evidence_exception_rows == 1
    assert report.structural_review_rows == 0
    assert report.review_exception_rows == 1
    assert report.exceptions[0].node_id == "n1"
    assert report.exceptions[0].reasons == ["LOW_TEXT_MATCH"]
    assert report.next_gate == "EXCEPTION_REVIEW"


def test_compile_report_never_auto_closes_unreviewed_structural_classification():
    locked = {
        "node_id": "n1",
        "chapter": 31,
        "proposed_final_classification": "REQUIRED_SUBSECTION",
        "review_status": "UNREVIEWED",
        "selected_pdf_page": 426,
    }
    report = build_compile_report(_packet(row=_row(locked=locked)))
    assert report.evidence_matched_rows == 1
    assert report.evidence_exception_rows == 0
    assert report.structural_review_rows == 1
    assert report.review_exception_rows == 1
    assert report.exceptions[0].reasons == [
        "STRUCTURAL_REVIEW_REQUIRED",
        "STRUCTURAL_STATUS_UNRESOLVED",
    ]


def test_compile_report_fails_closed_when_classification_is_missing():
    locked = {
        "node_id": "n1",
        "chapter": 31,
        "review_status": "PASS",
        "selected_pdf_page": 426,
    }
    report = build_compile_report(_packet(row=_row(locked=locked)))
    assert report.exceptions[0].reasons == ["CLASSIFICATION_MISSING"]


def test_compile_report_keeps_source_binding_as_a_separate_gate():
    report = build_compile_report(_packet(binding_state="ACCESS_GAP"))
    assert report.source_gate_passed is False
    assert report.next_gate == "SOURCE_BINDING_REVIEW"
    assert report.publish_authorized is False
