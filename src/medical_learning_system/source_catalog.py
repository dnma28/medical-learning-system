from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .drive_metadata import DriveFileMetadata, SourceAssignment
from .source_registry import SourceKind


class CatalogSource(BaseModel):
    logical_source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: SourceKind = SourceKind.OTHER
    domain: str | None = None
    edition: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    match_patterns: list[str] = Field(default_factory=list)
    part_pattern: str | None = None


class SourceCatalog(BaseModel):
    sources: list[CatalogSource]

    @classmethod
    def load(cls, path: Path) -> "SourceCatalog":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(payload)

    def classify(self, metadata: DriveFileMetadata) -> SourceAssignment:
        for source in self.sources:
            if any(re.search(pattern, metadata.title) for pattern in source.match_patterns):
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
