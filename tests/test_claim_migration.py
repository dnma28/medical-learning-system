from datetime import datetime, timezone
from pathlib import Path

from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.knowledge_graph.claim_migration import (
    ClaimMigrationState,
    build_claim_migration_ledger,
)
from medical_learning_system.knowledge_graph.source_anchor_resolution import (
    load_legacy_source_map,
)
from medical_learning_system.knowledge_graph.v5_migration import (
    migrate_v5_patch_text,
)
from medical_learning_system.source_registry import SourceKind, SourceRecord


SOURCE_MAP = Path("config/kg_v5_source_map.yaml")


def source():
    return SourceRecord(
        source_id="costanzo-physical",
        logical_source_id="costanzo-physiology",
        provider="google_drive",
        provider_file_id="drive-costanzo",
        title="Costanzo.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
        edition="6",
    )


def migration():
    return migrate_v5_patch_text(
        "electrophysiology",
        """
        {
          "patch_id":"foundation.electrochemical_membrane.v1"
        }
        {
          "source_anchors":[
            {
              "id":"sa-b08-ch1",
              "source_book_id":"b08",
              "edition":"6",
              "pdf_pages":[15],
              "verification_state":"PASS"
            },
            {
              "id":"sa-b06-gap",
              "source_book_id":"b06",
              "edition":"26",
              "verification_state":"GAP"
            },
            {
              "id":"sa-anchor-gap",
              "source_book_id":"b08",
              "edition":"6",
              "pdf_pages":[15],
              "verification_state":"GAP"
            }
          ],
          "claim_verification":[
            {
              "claim":"Na/K ATPase maintains ion gradients",
              "source_anchor_id":"sa-b08-ch1",
              "verification_state":"PASS"
            },
            {
              "claim":"Ganong wording",
              "source_anchor_id":"sa-b06-gap",
              "verification_state":"GAP"
            },
            {
              "claim":"unverified mechanism",
              "verification_state":"GAP"
            },
            {
              "claim":"missing target",
              "source_anchor_id":"does-not-exist",
              "verification_state":"PASS"
            },
            {
              "claim":"conflicting states",
              "source_anchor_id":"sa-anchor-gap",
              "verification_state":"PASS"
            }
          ]
        }
        """,
    )


def test_pass_claim_gets_candidate_evidence_but_still_requires_review():
    physical = source()
    block = make_evidence_block(
        source_id=physical.source_id,
        block_index=0,
        page_index=14,
        content_type=EvidenceContentType.TEXT,
        parser="native",
        text="ATPase source block",
    )

    ledger = build_claim_migration_ledger(
        migration(),
        source_map=load_legacy_source_map(SOURCE_MAP),
        sources=[physical],
        evidence=[block],
    )

    record = ledger.records[0]
    assert record.state == ClaimMigrationState.PASS_CANDIDATE_EVIDENCE
    assert record.evidence_ids == [block.evidence_id]
    assert record.passage_review_required is True


def test_gap_claim_is_never_upgraded():
    ledger = build_claim_migration_ledger(
        migration(),
        source_map=load_legacy_source_map(SOURCE_MAP),
        sources=[source()],
    )

    assert ledger.records[1].state == ClaimMigrationState.GAP
    assert ledger.records[2].state == ClaimMigrationState.GAP


def test_unknown_anchor_reference_is_explicit():
    ledger = build_claim_migration_ledger(
        migration(),
        source_map=load_legacy_source_map(SOURCE_MAP),
        sources=[source()],
    )

    assert ledger.records[3].state == ClaimMigrationState.UNKNOWN_ANCHOR_REFERENCE


def test_claim_pass_anchor_gap_is_verification_conflict():
    physical = source()
    block = make_evidence_block(
        source_id=physical.source_id,
        block_index=0,
        page_index=14,
        content_type=EvidenceContentType.TEXT,
        parser="native",
        text="candidate",
    )
    ledger = build_claim_migration_ledger(
        migration(),
        source_map=load_legacy_source_map(SOURCE_MAP),
        sources=[physical],
        evidence=[block],
    )

    assert ledger.records[4].state == ClaimMigrationState.VERIFICATION_CONFLICT


def test_ledger_reports_state_counts():
    ledger = build_claim_migration_ledger(
        migration(),
        source_map=load_legacy_source_map(SOURCE_MAP),
        sources=[source()],
    )

    assert ledger.total_claims == 5
    assert ledger.states["gap"] == 2
    assert ledger.states["unknown_anchor_reference"] == 1
    assert ledger.states["verification_conflict"] == 1
