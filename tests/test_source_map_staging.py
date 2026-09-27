import pytest

from medical_learning_system.source_map_staging import (
    LocatorKind,
    PointLocatorScope,
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


def test_verified_toc_identity_point_requires_exact_publisher_provenance():
    title = "PART I — SOURCE-VERIFIED STRUCTURE"
    node = StagingNode(
        node_id="part-i",
        title=title,
        parent_id="book",
        kind=StructureKind.PART,
        depth=1,
        order_index=1,
        locator_kind=LocatorKind.POINT,
        page_start=17,
        status=StagingStatus.VERIFIED,
        source_anchor={
            "scope": PointLocatorScope.TOC_IDENTITY.value,
            "publisher_surface": "contents",
            "identity_text": title,
            "body_heading_absent": True,
            "pdf_page": 17,
        },
    )
    assert node.page_end is None
    assert node.source_anchor["scope"] == "toc_identity_point_not_section_range"


@pytest.mark.parametrize(
    ("anchor_patch", "message"),
    [
        ({"publisher_surface": "body"}, "publisher Contents/TOC"),
        ({"identity_text": "fuzzy equivalent"}, "exact identity_text"),
        ({"body_heading_absent": False}, "body_heading_absent=true"),
        ({"pdf_page": 18}, "pdf_page must match page_start"),
    ],
)
def test_verified_toc_identity_point_rejects_weak_provenance(anchor_patch, message):
    title = "PART I — SOURCE-VERIFIED STRUCTURE"
    anchor = {
        "scope": PointLocatorScope.TOC_IDENTITY.value,
        "publisher_surface": "contents",
        "identity_text": title,
        "body_heading_absent": True,
        "pdf_page": 17,
        **anchor_patch,
    }
    with pytest.raises(ValueError, match=message):
        StagingNode(
            node_id="part-i",
            title=title,
            kind=StructureKind.PART,
            locator_kind=LocatorKind.POINT,
            page_start=17,
            status=StagingStatus.VERIFIED,
            source_anchor=anchor,
        )


def test_verified_toc_identity_point_requires_page_and_structural_kind():
    title = "PART I — SOURCE-VERIFIED STRUCTURE"
    anchor = {
        "scope": PointLocatorScope.TOC_IDENTITY.value,
        "publisher_surface": "toc",
        "identity_text": title,
        "body_heading_absent": True,
        "pdf_page": 17,
    }
    with pytest.raises(ValueError, match="requires page_start"):
        StagingNode(
            node_id="part-i",
            title=title,
            kind=StructureKind.PART,
            locator_kind=LocatorKind.POINT,
            status=StagingStatus.VERIFIED,
            source_anchor=anchor,
        )
    with pytest.raises(ValueError, match="structural node kind"):
        StagingNode(
            node_id="other",
            title=title,
            kind=StructureKind.OTHER,
            locator_kind=LocatorKind.POINT,
            page_start=17,
            status=StagingStatus.VERIFIED,
            source_anchor=anchor,
        )


def test_heading_point_semantic_remains_backward_compatible():
    node = StagingNode(
        node_id="section",
        title="Exact body heading",
        kind=StructureKind.SECTION,
        locator_kind=LocatorKind.POINT,
        page_start=42,
        status=StagingStatus.VERIFIED,
        source_anchor={
            "scope": PointLocatorScope.HEADING.value,
            "pdf_page": 42,
        },
    )
    assert node.source_anchor["scope"] == "heading_point_not_section_range"
    assert node.page_end is None
