import hashlib
import json

from medical_learning_system.source_map_batch import (
    BatchScope,
    DecisionSet,
    EvidenceBlock,
    SourceIdentity,
    build_review_packet,
    evidence_pages_for_rows,
    evidence_pages_for_scope,
    validate_decisions,
    validate_manifest_scope,
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



def _scope():
    return BatchScope(
        work_key="source-map:neumann-kinesiology:b12",
        unit_field="chapter",
        authorized_units=[12],
        expected_counts={"12": 2},
        expected_total=2,
        pdf_page_start=11,
        pdf_page_end=13,
        reverse_coverage_required=True,
    )


def test_manifest_scope_rejects_scope_drift_and_wrong_population():
    metadata = {"scope": _scope().model_dump(mode="json")}
    assert validate_manifest_scope(metadata, _rows(), required=True) == _scope()

    drifted = [*_rows(), {**_rows()[0], "node_id": "n3", "chapter": 13}]
    import pytest
    with pytest.raises(ValueError, match="outside authorized scope"):
        validate_manifest_scope(metadata, drifted, required=True)


def test_reverse_coverage_expands_to_full_physical_scope():
    pages = evidence_pages_for_scope(
        _rows(),
        scope=_scope(),
        neighbor_pages=1,
        page_count=20,
    )
    assert pages == [11, 12, 13]


def test_reverse_coverage_rejects_candidate_escape():
    scope = _scope().model_copy(update={"pdf_page_start": 13, "pdf_page_end": 15})
    import pytest
    with pytest.raises(ValueError, match="candidate pages escape"):
        evidence_pages_for_scope(_rows(), scope=scope, page_count=20)


def test_scoped_packet_requires_decision_binding_to_work_manifest_and_scope():
    packet = build_review_packet(
        batch_id="BATCH-12",
        manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
        rows=_rows(),
        source=_source(),
        blocks=[],
        scope=_scope(),
    )
    unbound = DecisionSet(
        batch_id="BATCH-12",
        decisions=[
            {"node_id": "n1", "disposition": "REVIEW_REQUIRED"},
            {"node_id": "n2", "disposition": "REVIEW_REQUIRED"},
        ],
    )
    errors = validate_decisions(packet, unbound)
    assert any("work_key mismatch" in error for error in errors)
    assert any("manifest_sha256" in error for error in errors)
    assert any("scope_sha256" in error for error in errors)

    bound = DecisionSet(
        batch_id="BATCH-12",
        work_key=packet.work_key,
        manifest_sha256=packet.manifest_sha256,
        scope_sha256=packet.scope_sha256,
        decisions=[
            {"node_id": "n1", "disposition": "REVIEW_REQUIRED"},
            {"node_id": "n2", "disposition": "REVIEW_REQUIRED"},
        ],
    )
    assert validate_decisions(packet, bound) == []



def test_scoped_packet_keeps_full_reverse_coverage_blocks():
    scope = _scope()
    blocks = [
        EvidenceBlock(
            page=11, block_index=0, text="Omitted source parent",
            bbox=(1, 1, 10, 10), font_sizes=[12.0], fonts=["Bold"],
        ),
        EvidenceBlock(
            page=12, block_index=1, text="Hip Flexor Muscles",
            bbox=(1, 20, 10, 30), font_sizes=[12.0], fonts=["Bold"],
        ),
        EvidenceBlock(
            page=13, block_index=0, text="Boundary structural heading",
            bbox=(1, 1, 10, 10), font_sizes=[10.0], fonts=["Bold"],
        ),
    ]
    packet = build_review_packet(
        batch_id="BATCH-12",
        manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
        rows=_rows(),
        source=_source(),
        blocks=blocks,
        scope=scope,
        evidence_pages=[11, 12, 13],
    )
    assert [(block.page, block.block_index) for block in packet.scope_blocks] == [
        (11, 0), (12, 1), (13, 0)
    ]


def test_classification_scope_validates_topology_and_augmentations():
    scope = _scope().model_copy(update={"classification_required": True})
    packet = build_review_packet(
        batch_id="BATCH-12",
        manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
        rows=_rows(),
        source=_source(),
        blocks=[
            EvidenceBlock(
                page=13,
                block_index=0,
                text="Exact missing child",
                bbox=(1, 1, 10, 10),
            )
        ],
        scope=scope,
    )
    decisions = DecisionSet(
        batch_id=packet.batch_id,
        work_key=packet.work_key,
        manifest_sha256=packet.manifest_sha256,
        scope_sha256=packet.scope_sha256,
        scope_evidence_sha256=packet.scope_evidence_sha256,
        decisions=[
            {
                "node_id": "n1",
                "resolution_status": "VERIFIED",
                "final_classification": "REQUIRED_SECTION",
            },
            {
                "node_id": "n2",
                "resolution_status": "VERIFIED",
                "final_classification": "REQUIRED_SUBSECTION",
                "canonical_parent_observation_id": "n1",
            },
        ],
        augmentations=[
            {
                "augmentation_observation_id": "aug-1",
                "unit_value": 12,
                "pdf_page": 13,
                "physical_block_indices": [0],
                "exact_source_text": "Exact missing child",
                "bbox": [1, 1, 10, 10],
                "source_id": packet.source.source_id,
                "source_sha256": packet.source.content_sha256,
                "source_observed": True,
                "final_classification": "REQUIRED_SUBSECTION",
                "canonical_parent_observation_id": "n1",
            }
        ],
    )
    assert validate_decisions(packet, decisions) == []

    broken = decisions.model_copy(deep=True)
    broken.decisions[1].canonical_parent_observation_id = "missing"
    assert any("missing parent" in error for error in validate_decisions(packet, broken))

    wrong_text = decisions.model_copy(deep=True)
    wrong_text.augmentations[0].exact_source_text = "asserted text absent from PDF packet"
    assert any(
        "exact_source_text does not match" in error
        for error in validate_decisions(packet, wrong_text)
    )

    wrong_bbox = decisions.model_copy(deep=True)
    wrong_bbox.augmentations[0].bbox = (2, 2, 11, 11)
    assert any(
        "bbox does not match" in error
        for error in validate_decisions(packet, wrong_bbox)
    )

    tampered_packet = packet.model_copy(deep=True)
    tampered_packet.scope_blocks[0].text = "Changed after packet creation"
    assert any(
        "packet scope evidence digest mismatch" in error
        for error in validate_decisions(tampered_packet, decisions)
    )

    missing_block_packet = packet.model_copy(deep=True)
    missing_block_packet.scope_blocks = []
    assert any(
        "physical source block is missing" in error
        for error in validate_decisions(missing_block_packet, decisions)
    )


def test_classification_scope_rejects_out_of_scope_augmentation_and_cross_unit_parent():
    scope = _scope().model_copy(update={"classification_required": True})
    packet = build_review_packet(
        batch_id="BATCH-12",
        manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
        rows=_rows(),
        source=_source(),
        blocks=[],
        scope=scope,
    )
    decisions = DecisionSet(
        batch_id=packet.batch_id,
        work_key=packet.work_key,
        manifest_sha256=packet.manifest_sha256,
        scope_sha256=packet.scope_sha256,
        decisions=[
            {
                "node_id": "n1",
                "resolution_status": "VERIFIED",
                "final_classification": "REQUIRED_SECTION",
            },
            {
                "node_id": "n2",
                "resolution_status": "VERIFIED",
                "final_classification": "REQUIRED_SUBSECTION",
                "canonical_parent_observation_id": "aug-out",
            },
        ],
        augmentations=[
            {
                "augmentation_observation_id": "aug-out",
                "unit_value": 13,
                "pdf_page": 13,
                "physical_block_indices": [0],
                "exact_source_text": "Wrong chapter",
                "bbox": [1, 1, 10, 10],
                "source_id": packet.source.source_id,
                "source_sha256": packet.source.content_sha256,
                "source_observed": True,
                "final_classification": "REQUIRED_SECTION",
            }
        ],
    )
    errors = validate_decisions(packet, decisions)
    assert any("outside authorized scope" in error for error in errors)
    assert any("crosses scope unit" in error for error in errors)
