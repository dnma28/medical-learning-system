from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ValidationStatus(str, Enum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"


class SourceLocator(BaseModel):
    source_id: str
    title: str | None = None
    chapter: str | None = None
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    quote_hash: str | None = None

    @model_validator(mode="after")
    def has_locator(self) -> "SourceLocator":
        if self.page is None and not self.chapter and not self.section:
            raise ValueError("Evidence needs page, chapter, or section provenance")
        return self


class Evidence(BaseModel):
    locator: SourceLocator
    claim_text: str = Field(min_length=3)
    extractor: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class GraphNode(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation_status: ValidationStatus = ValidationStatus.CANDIDATE
    evidence: list[Evidence] = Field(default_factory=list)


class GraphEdge(BaseModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    target: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation_status: ValidationStatus = ValidationStatus.CANDIDATE
    evidence: list[Evidence] = Field(default_factory=list)
