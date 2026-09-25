import pytest

from medical_learning_system.source_map_staging import (
    LocatorKind,
    StagingNode,
    StagingSourceMap,
    StagingStatus,
)


def test_draft_preserves_unknown_hierarchy_source_gap_and_unassigned_curriculum():
    staged = StagingSourceMap(
        logical_source_id="book",
        staging_version=1,
        proposal=[
            StagingNode(
                node_id="unknown-parent", title="Unit A", parent_id="unresolved",
                kind=None, depth=None, order_index=None, status=StagingStatus.SOURCE_GAP,
                locator_kind=LocatorKind.UNRESOLVED, confidence=0.25,
                evidence={"note": "needs source review"},
                issues=[{"reason": "PARENT_OR_LEVEL_UNRESOLVED"}],
            )
        ],
    )
    assert staged.toc_denominator is None
    assert staged.proposal[0].learning_value is None
    assert staged.proposal[0].parent_id == "unresolved"
    assert staged.proposal[0].source_id is None


def test_point_anchor_does_not_claim_range():
    with pytest.raises(ValueError, match="point locator"):
        StagingNode(node_id="x", title="X", locator_kind=LocatorKind.POINT,
                    page_start=1, page_end=2)


def test_verified_range_requires_end_evidence():
    with pytest.raises(ValueError, match="evidenced page_end"):
        StagingNode(node_id="x", title="X", locator_kind=LocatorKind.VERIFIED_RANGE,
                    page_start=1)


def test_stage_rejects_duplicate_node_ids():
    with pytest.raises(ValueError, match="duplicate"):
        StagingSourceMap(
            logical_source_id="book", staging_version=2,
            proposal=[StagingNode(node_id="x", title="A"),
                      StagingNode(node_id="x", title="B")],
        )
