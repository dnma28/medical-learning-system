from __future__ import annotations

import hashlib
import re
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from .drive_metadata import DriveFileMetadata, SourceAssignment
from .source_registry import SourceKind


class IdentityStatus(str, Enum):
    VERIFIED = "verified"
    VERIFY_FROM_SOURCE = "verify_from_source"
    POTENTIAL_DUPLICATE = "potential_duplicate"


class SourceMapState(str, Enum):
    UNMAPPED = "unmapped"
    TOC_MAPPED = "toc_mapped"
    SECTION_ANCHORED = "section_anchored"
    DEEP_ANCHORED = "deep_anchored"
    READY_FOR_HOC90 = "ready_for_hoc90"


class CatalogSource(BaseModel):
    logical_source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: SourceKind = SourceKind.OTHER
    domain: str | None = None
    edition: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)

    role: str | None = None
    identity_status: IdentityStatus = IdentityStatus.VERIFY_FROM_SOURCE
    source_map_state: SourceMapState = SourceMapState.UNMAPPED

    # Exact Drive file IDs are optional operational identities. Filename
    # patterns remain the portable fallback when a catalog is reused elsewhere.
    provider_file_ids: list[str] = Field(default_factory=list)
    canonical_provider_file_id: str | None = None
    alternate_provider_file_ids: list[str] = Field(default_factory=list)

    match_patterns: list[str] = Field(default_factory=list)
    part_pattern: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_file_roles(self) -> "CatalogSource":
        exact = set(self.provider_file_ids)
        if self.canonical_provider_file_id and self.canonical_provider_file_id not in exact:
            raise ValueError("canonical_provider_file_id must be in provider_file_ids")
        unknown_alternates = set(self.alternate_provider_file_ids) - exact
        if unknown_alternates:
            raise ValueError(
                "alternate_provider_file_ids must be in provider_file_ids"
            )
        return self

    def matches(self, metadata: DriveFileMetadata) -> bool:
        if metadata.file_id in self.provider_file_ids:
            return True
        return any(re.search(pattern, metadata.title) for pattern in self.match_patterns)


class SourceCatalog(BaseModel):
    sources: list[CatalogSource]

    @model_validator(mode="after")
    def validate_unique_identities(self) -> "SourceCatalog":
        logical_ids = [source.logical_source_id for source in self.sources]
        if len(logical_ids) != len(set(logical_ids)):
            raise ValueError("duplicate logical_source_id in catalog")

        owner_by_file: dict[str, str] = {}
        for source in self.sources:
            for file_id in source.provider_file_ids:
                existing = owner_by_file.get(file_id)
                if existing and existing != source.logical_source_id:
                    raise ValueError(
                        f"Drive file {file_id} belongs to multiple logical sources"
                    )
                owner_by_file[file_id] = source.logical_source_id
        return self

    @classmethod
    def load(cls, path: Path) -> "SourceCatalog":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(payload)

    def get(self, logical_source_id: str) -> CatalogSource:
        for source in self.sources:
            if source.logical_source_id == logical_source_id:
                return source
        raise KeyError(logical_source_id)

    def classify(self, metadata: DriveFileMetadata) -> SourceAssignment:
        for source in self.sources:
            if source.matches(metadata):
                part_index = None
                if source.part_pattern:
                    match = re.search(source.part_pattern, metadata.title)
                    if match:
                        part_index = int(match.group(1))

                return SourceAssignment(
                    logical_source_id=source.logical_source_id,
                    kind=source.kind,
                    domain=source.domain,
                    edition=source.edition,
                    publication_year=source.publication_year,
                    part_index=part_index,
                )

        suffix = hashlib.sha256(metadata.file_id.encode("utf-8")).hexdigest()[:12]
        return SourceAssignment(logical_source_id=f"unclassified--{suffix}")
