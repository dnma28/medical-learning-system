"""Compact one-book Source Map compile facade.

This module deliberately reuses the bounded Source Map batch engine. It only
prepares immutable review evidence and a finite exception report; it never
stages, certifies, promotes, or writes runtime state.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .source_map_batch import (
    ReviewPacket,
    ReviewPacketRow,
    canonical_sha256,
    prepare_from_pdf,
)


COMPILE_SCHEMA_VERSION = "book-compile-v1"
_EXACT_BINDINGS = {"EXACT_MATCH", "VERIFIED_CANONICAL"}
_UNRESOLVED_MARKERS = (
    "REVIEW_REQUIRED",
    "UNREVIEWED",
    "SOURCE_GAP",
    "ACCESS_GAP",
    "SOURCE_CORRUPTION_GAP",
)


class CompileException(BaseModel):
    node_id: str = Field(min_length=1)
    reasons: list[str] = Field(min_length=1)


class BookCompileReport(BaseModel):
    schema_version: str = COMPILE_SCHEMA_VERSION
    batch_id: str
    work_key: str | None = None
    logical_source_id: str
    source_id: str
    source_sha256: str
    source_pages: int | None = None
    source_binding_state: str
    source_gate_passed: bool
    packet_sha256: str
    total_rows: int = Field(ge=0)
    evidence_matched_rows: int = Field(ge=0)
    evidence_exception_rows: int = Field(ge=0)
    structural_review_rows: int = Field(ge=0)
    review_exception_rows: int = Field(ge=0)
    exceptions: list[CompileException] = Field(default_factory=list)
    next_gate: str
    publish_authorized: bool = False


def _status_text(row: ReviewPacketRow) -> str:
    fields = ("review_status", "resolution_status", "status")
    return " ".join(
        str(row.locked.get(field) or "").upper()
        for field in fields
    )


def exception_reasons(
    row: ReviewPacketRow,
    *,
    classification_required: bool,
) -> list[str]:
    """Return only deterministic reasons that still need review."""

    reasons = list(row.evidence.visual_required_reasons)
    status = _status_text(row)
    if any(marker in status for marker in _UNRESOLVED_MARKERS):
        reasons.append("STRUCTURAL_STATUS_UNRESOLVED")

    if classification_required:
        classification = (
            row.locked.get("final_classification")
            or row.locked.get("proposed_final_classification")
        )
        if not classification:
            reasons.append("CLASSIFICATION_MISSING")
        independently_closed = (
            "PASS" in status or "VERIFIED" in status
        ) and not any(marker in status for marker in _UNRESOLVED_MARKERS)
        if not independently_closed:
            reasons.append("STRUCTURAL_REVIEW_REQUIRED")

    return sorted(set(reasons))


def build_compile_report(packet: ReviewPacket) -> BookCompileReport:
    classification_required = bool(
        packet.scope is not None and packet.scope.classification_required
    )
    exceptions = [
        CompileException(
            node_id=row.node_id,
            reasons=exception_reasons(
                row,
                classification_required=classification_required,
            ),
        )
        for row in packet.rows
        if exception_reasons(
            row,
            classification_required=classification_required,
        )
    ]
    evidence_matched = sum(
        not row.evidence.visual_required_reasons
        for row in packet.rows
    )
    evidence_exception_rows = sum(
        bool(row.evidence.visual_required_reasons)
        for row in packet.rows
    )
    structural_reasons = {
        "CLASSIFICATION_MISSING",
        "STRUCTURAL_REVIEW_REQUIRED",
        "STRUCTURAL_STATUS_UNRESOLVED",
    }
    structural_review_rows = sum(
        bool(structural_reasons.intersection(item.reasons))
        for item in exceptions
    )
    source_gate_passed = packet.source.binding_state.upper() in _EXACT_BINDINGS
    if not source_gate_passed:
        next_gate = "SOURCE_BINDING_REVIEW"
    elif exceptions:
        next_gate = "EXCEPTION_REVIEW"
    else:
        next_gate = "INDEPENDENT_REVIEW"

    return BookCompileReport(
        batch_id=packet.batch_id,
        work_key=packet.work_key,
        logical_source_id=packet.source.logical_source_id,
        source_id=packet.source.source_id,
        source_sha256=packet.source.content_sha256,
        source_pages=packet.source.page_count,
        source_binding_state=packet.source.binding_state,
        source_gate_passed=source_gate_passed,
        packet_sha256=canonical_sha256(packet.model_dump(mode="json")),
        total_rows=len(packet.rows),
        evidence_matched_rows=evidence_matched,
        evidence_exception_rows=evidence_exception_rows,
        structural_review_rows=structural_review_rows,
        review_exception_rows=len(exceptions),
        exceptions=exceptions,
        next_gate=next_gate,
    )


def compile_book_from_pdf(
    *,
    manifest_path: Path,
    pdf_path: Path,
    packet_path: Path,
    report_path: Path,
    cache_dir: Path,
    batch_id: str,
    logical_source_id: str,
    source_id: str,
    provider_file_id: str | None,
    binding_state: str,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    point_locator_only: bool = True,
    allowed_dispositions: list[str] | None = None,
) -> tuple[ReviewPacket, BookCompileReport]:
    """Prepare one bounded book packet and its compact exception report."""

    packet = prepare_from_pdf(
        manifest_path=manifest_path,
        pdf_path=pdf_path,
        output_path=packet_path,
        cache_dir=cache_dir,
        batch_id=batch_id,
        logical_source_id=logical_source_id,
        source_id=source_id,
        provider_file_id=provider_file_id,
        binding_state=binding_state,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
        point_locator_only=point_locator_only,
        allowed_dispositions=allowed_dispositions,
        require_scope=True,
    )
    report = build_compile_report(packet)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return packet, report
