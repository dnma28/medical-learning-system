from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SourceManifest(BaseModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    edition: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    logical_book_id: str | None = None
    notes: str | None = None


def load_manifest(path: Path) -> SourceManifest:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourceManifest.model_validate(payload)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
