from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import BaseModel, Field, model_validator

from ..evidence_store import SourceEvidenceBlock
from ..source_registry import SourceRecord


_PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


class AnchorIdentityState(str, Enum):
    RESOLVED = "resolved"
    UNMAPPED_LEGACY_SOURCE = "unmapped_legacy_source"
    NO_REGISTERED_SOURCE = "no_registered_source"
    EDITION_MISMATCH = "edition_mismatch"
    AMBIGUOUS_PHYSICAL_SOURCE = "ambiguous_physical_source"


class LegacySourceMapping(BaseModel):
    legacy_source_book_id: str = Field(min_length=1)
    logical_source_id: str = Field(min_length=1)
    verified_from: str = Field(min_length=1)
    note: str | None = None


class LegacySourceMap(BaseModel):
    mappings: list[LegacySourceMapping]

    @model_validator(mode="after")
    def unique_legacy_ids(self) -> "LegacySourceMap":
        ids = [item.legacy_source_book_id for item in self.mappings]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate legacy_source_book_id")
        return self

    def get(self, legacy_source_book_id: str) -> LegacySourceMapping | None:
        return next(
            (
                item
                for item in self.mappings
                if item.legacy_source_book_id == legacy_source_book_id
            ),
            None,
        )


class SourceAnchorResolution(BaseModel):
    anchor_id: str | None = None
    legacy_source_book_id: str | None = None
    logical_source_id: str | None = None
    source_id: str | None = None
    anchor_verification_state: str | None = None
    identity_state: AnchorIdentityState
    explicit_pdf_pages: list[int] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    canonical_evidence_ready: bool = False
    notes: list[str] = Field(default_factory=list)


def load_legacy_source_map(path: Path) -> LegacySourceMap:
    return LegacySourceMap.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )


def resolve_source_anchor(
    anchor: dict[str, Any],
    *,
    source_map: LegacySourceMap,
    sources: Iterable[SourceRecord],
    evidence: Iterable[SourceEvidenceBlock] = (),
) -> SourceAnchorResolution:
    anchor_id = _optional_string(anchor.get("id"))
    legacy_id = _optional_string(anchor.get("source_book_id"))
    verification = _optional_string(
        anchor.get("source_anchor_state", anchor.get("verification_state"))
    )
    pages, page_notes = explicit_pdf_pages(anchor)

    if legacy_id is None:
        return SourceAnchorResolution(
            anchor_id=anchor_id,
            anchor_verification_state=verification,
            identity_state=AnchorIdentityState.UNMAPPED_LEGACY_SOURCE,
            explicit_pdf_pages=pages,
            notes=["source anchor has no source_book_id", *page_notes],
        )

    mapping = source_map.get(legacy_id)
    if mapping is None:
        return SourceAnchorResolution(
            anchor_id=anchor_id,
            legacy_source_book_id=legacy_id,
            anchor_verification_state=verification,
            identity_state=AnchorIdentityState.UNMAPPED_LEGACY_SOURCE,
            explicit_pdf_pages=pages,
            notes=[
                f"no explicit mapping registered for {legacy_id}",
                *page_notes,
            ],
        )

    candidates = [
        source
        for source in sources
        if source.logical_source_id == mapping.logical_source_id
    ]
    if not candidates:
        return SourceAnchorResolution(
            anchor_id=anchor_id,
            legacy_source_book_id=legacy_id,
            logical_source_id=mapping.logical_source_id,
            anchor_verification_state=verification,
            identity_state=AnchorIdentityState.NO_REGISTERED_SOURCE,
            explicit_pdf_pages=pages,
            notes=["logical source has no registered physical source", *page_notes],
        )

    edition = _optional_string(anchor.get("edition"))
    if edition:
        edition_matches = [
            source for source in candidates if source.edition == edition
        ]
        if not edition_matches:
            return SourceAnchorResolution(
                anchor_id=anchor_id,
                legacy_source_book_id=legacy_id,
                logical_source_id=mapping.logical_source_id,
                anchor_verification_state=verification,
                identity_state=AnchorIdentityState.EDITION_MISMATCH,
                explicit_pdf_pages=pages,
                notes=[
                    f"anchor edition {edition!r} has no exact registered match",
                    *page_notes,
                ],
            )
        candidates = edition_matches

    if len(candidates) != 1:
        return SourceAnchorResolution(
            anchor_id=anchor_id,
            legacy_source_book_id=legacy_id,
            logical_source_id=mapping.logical_source_id,
            anchor_verification_state=verification,
            identity_state=AnchorIdentityState.AMBIGUOUS_PHYSICAL_SOURCE,
            explicit_pdf_pages=pages,
            notes=[
                (
                    f"{len(candidates)} physical sources match; resolver will "
                    "not choose by filename"
                ),
                *page_notes,
            ],
        )

    source = candidates[0]
    evidence_ids = sorted(
        block.evidence_id
        for block in evidence
        if block.source_id == source.source_id
        and block.pdf_page in set(pages)
    )

    notes = list(page_notes)
    if not pages:
        notes.append(
            "no explicit PDF page locator; chapter/section text was not used "
            "to invent a page"
        )
    elif not evidence_ids:
        notes.append("explicit pages resolved but no stored evidence block matched")

    ready = (
        (verification or "").upper() == "PASS"
        and bool(evidence_ids)
    )
    if (verification or "").upper() != "PASS":
        notes.append(
            "anchor verification is not PASS; identity/evidence resolution "
            "does not upgrade its verification state"
        )

    return SourceAnchorResolution(
        anchor_id=anchor_id,
        legacy_source_book_id=legacy_id,
        logical_source_id=mapping.logical_source_id,
        source_id=source.source_id,
        anchor_verification_state=verification,
        identity_state=AnchorIdentityState.RESOLVED,
        explicit_pdf_pages=pages,
        evidence_ids=evidence_ids,
        canonical_evidence_ready=ready,
        notes=notes,
    )


def explicit_pdf_pages(
    anchor: dict[str, Any],
) -> tuple[list[int], list[str]]:
    pages: set[int] = set()
    notes: list[str] = []

    for field in ("pdf_page", "page", "pdf_start_page"):
        value = anchor.get(field)
        if isinstance(value, int) and value >= 1:
            pages.add(value)

    values = anchor.get("pdf_pages")
    if isinstance(values, list):
        pages.update(
            value for value in values if isinstance(value, int) and value >= 1
        )

    page_range = anchor.get("pdf_page_range")
    if isinstance(page_range, str) and page_range.strip():
        match = _PAGE_RANGE_RE.fullmatch(page_range)
        if match is None:
            notes.append(
                f"unparsed pdf_page_range {page_range!r}; no repair attempted"
            )
        else:
            start, end = (int(match.group(1)), int(match.group(2)))
            if end < start:
                notes.append(
                    f"reversed pdf_page_range {page_range!r}; ignored"
                )
            else:
                pages.update(range(start, end + 1))

    return sorted(pages), notes


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
