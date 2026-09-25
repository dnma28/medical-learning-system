"""Curriculum-neutral, immutable-version Source Map staging payload.

The staging tree deliberately permits unresolved parents and missing locators.
Only database certification/promotion may impose the strict runtime contract.
"""

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .coverage import StructureKind
from .source_map import LearningValue


class StagingStatus(str, Enum):
    CANDIDATE = "candidate"
    REVIEW_REQUIRED = "review_required"
    SOURCE_GAP = "source_gap"
    VERIFIED = "verified"


class LocatorKind(str, Enum):
    UNRESOLVED = "unresolved"
    POINT = "point"
    VERIFIED_RANGE = "verified_range"


class StagingNode(BaseModel):
    node_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    parent_id: str | None = None
    kind: StructureKind | None = None
    depth: int | None = Field(default=None, ge=0)
    order_index: int | None = Field(default=None, ge=0)
    source_id: str | None = None
    locator_kind: LocatorKind = LocatorKind.UNRESOLVED
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_anchor: dict[str, object] = Field(default_factory=dict)
    source_sha256: str | None = None
    extraction_sha256: str | None = None
    extraction_version: str | None = None
    status: StagingStatus = StagingStatus.CANDIDATE
    required: bool = True
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: dict[str, object] = Field(default_factory=dict)
    issues: list[dict[str, object]] = Field(default_factory=list)
    learning_value: LearningValue | None = None
    freshness_required: bool = False

    @model_validator(mode="after")
    def check_locator_claim(self) -> "StagingNode":
        if self.page_end is not None and self.page_start is None:
            raise ValueError("page_end requires page_start")
        if (self.page_end is not None and self.page_start is not None
                and self.page_end < self.page_start):
            raise ValueError("page_end precedes page_start")
        if self.locator_kind == LocatorKind.POINT and self.page_end is not None:
            raise ValueError("point locator cannot claim a range")
        if self.locator_kind == LocatorKind.VERIFIED_RANGE and self.page_end is None:
            raise ValueError("verified range needs an evidenced page_end")
        return self


class StagingSourceMap(BaseModel):
    logical_source_id: str = Field(min_length=1)
    staging_version: int = Field(ge=1)
    proposal: list[StagingNode] = Field(min_length=1)
    toc_denominator: int | None = Field(default=None, ge=1)
    extraction_version: str | None = None
    source_manifest: dict[str, object] = Field(default_factory=dict)
    audit_metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_node_ids(self) -> "StagingSourceMap":
        ids = [node.node_id for node in self.proposal]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate staged node ID")
        return self
