from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .coverage import StructureKind
from .source_catalog import SourceMapState


class LearningValue(str, Enum):
    CORE_MASTERY = "core_mastery"
    SUPPORTING = "supporting"
    REFERENCE_ONLY = "reference_only"
    CURRENT_CLINICAL_CHECK = "current_clinical_check"


class SourceMapNode(BaseModel):
    logical_source_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    parent_id: str | None = None
    kind: StructureKind
    title: str = Field(min_length=1)
    depth: int = Field(ge=0)
    order_index: int = Field(ge=0)

    # Optional physical source anchor. A logical book can span many PDFs.
    # Any physical locator is meaningful only when its exact source_id is known.
    source_id: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_anchor: dict[str, object] = Field(default_factory=dict)

    # Source structure is curriculum neutral until that decision is made.
    learning_value: LearningValue | None = None
    freshness_required: bool = False

    @model_validator(mode="after")
    def validate_page_range(self) -> "SourceMapNode":
        has_physical_locator = (
            self.page_start is not None
            or self.page_end is not None
            or bool(self.source_anchor)
        )
        if has_physical_locator and self.source_id is None:
            raise ValueError("physical Source Map locator requires source_id")
        if self.page_end is not None and self.page_start is None:
            raise ValueError("page_end requires page_start")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be >= page_start")
        if self.learning_value == LearningValue.CURRENT_CLINICAL_CHECK and not self.freshness_required:
            raise ValueError(
                "CURRENT_CLINICAL_CHECK nodes must require freshness verification"
            )
        return self


class SourceMapCompleteness(BaseModel):
    logical_source_id: str
    structural_nodes: int = Field(ge=0)
    anchored_nodes: int = Field(ge=0)
    unanchored_node_ids: list[str]
    open_ended_page_node_ids: list[str]
    ready_for_hoc90: bool
    readiness_blockers: list[str]


class LogicalSourceMap(BaseModel):
    logical_source_id: str = Field(min_length=1)
    state: SourceMapState
    nodes: list[SourceMapNode]

    @model_validator(mode="after")
    def validate_tree(self) -> "LogicalSourceMap":
        validate_source_map(self.logical_source_id, self.nodes)
        return self

    def completeness(self) -> SourceMapCompleteness:
        structural = [node for node in self.nodes if node.kind != StructureKind.BOOK]
        anchored = [node for node in structural if node.source_id is not None]
        unanchored = [node.node_id for node in structural if node.source_id is None]
        open_ended = [
            node.node_id
            for node in structural
            if node.page_start is not None and node.page_end is None
        ]
        return SourceMapCompleteness(
            logical_source_id=self.logical_source_id,
            structural_nodes=len(structural),
            anchored_nodes=len(anchored),
            unanchored_node_ids=unanchored,
            open_ended_page_node_ids=open_ended,
            # Binding is only one dimension. A map without a certified printed/body
            # TOC denominator, locator QA and source/version evidence is never ready.
            # The state label is historical metadata, not an audit certificate.
            ready_for_hoc90=False,
            readiness_blockers=[
                "authoritative_toc_denominator_unverified",
                "required_toc_coverage_unverified",
                "locator_anchor_qa_unverified",
                "source_fingerprint_unverified",
                "extraction_version_unverified",
                "hierarchy_and_unresolved_issues_unverified",
            ] + (["physical_binding_missing"] if unanchored else []),
        )


def validate_source_map(
    logical_source_id: str,
    nodes: list[SourceMapNode],
) -> None:
    if not nodes:
        raise ValueError("source map must contain at least one node")

    if any(node.logical_source_id != logical_source_id for node in nodes):
        raise ValueError("all Source Map nodes must belong to the logical source")

    ids = [node.node_id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate Source Map node_id")

    orders = [node.order_index for node in nodes]
    if len(orders) != len(set(orders)):
        raise ValueError("duplicate Source Map order_index")

    by_id = {node.node_id: node for node in nodes}
    roots = [node for node in nodes if node.parent_id is None]
    if len(roots) != 1:
        raise ValueError("Source Map must contain exactly one root")

    root = roots[0]
    if root.kind != StructureKind.BOOK or root.depth != 0:
        raise ValueError("Source Map root must be a book node at depth 0")

    for node in nodes:
        if node is root:
            continue
        if node.parent_id not in by_id:
            raise ValueError(f"missing Source Map parent for {node.node_id}")
        parent = by_id[node.parent_id]
        if node.depth != parent.depth + 1:
            raise ValueError(f"invalid Source Map depth for {node.node_id}")
        if node.order_index <= parent.order_index:
            raise ValueError(f"child must follow parent for {node.node_id}")
        allowed_parents = {
            StructureKind.PART: {StructureKind.BOOK},
            StructureKind.UNIT: {StructureKind.BOOK},
            StructureKind.CHAPTER: {
                StructureKind.BOOK, StructureKind.PART, StructureKind.UNIT
            },
            StructureKind.SECTION: {StructureKind.CHAPTER},
            StructureKind.SUBSECTION: {StructureKind.SECTION, StructureKind.SUBSECTION},
        }
        # OTHER remains readable for legacy non-structural entries. It must
        # never stand in for a Part or Unit in newly certified Source Maps.
        if node.kind in allowed_parents and parent.kind not in allowed_parents[node.kind]:
            raise ValueError(f"invalid Source Map parent kind for {node.node_id}")
