from __future__ import annotations

import hashlib
import json
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .native_pdf_text import native_pdf_page_count
from .sources import sha256_file


SCHEMA_VERSION = "1.4.0"
BLOCK_CACHE_VERSION = "page-blocks-v2"
_DEFAULT_HEADING_FIELDS = (
    "heading_expected_raw",
    "heading_expected_normalized",
    "heading_text_visually_corrected",
    "heading_text_pdf_layer_raw",
    "title",
)
_GAP_MARKERS = ("ACCESS_GAP", "SOURCE_GAP", "SOURCE_CORRUPTION_GAP")
_EXACT_BINDINGS = {"EXACT_MATCH", "VERIFIED_CANONICAL"}


class SourceIdentity(BaseModel):
    logical_source_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    provider_file_id: str | None = None
    content_sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    page_count: int | None = Field(default=None, ge=1)
    binding_state: str = Field(min_length=1)


class EvidenceSpan(BaseModel):
    line_index: int = Field(ge=0)
    span_index: int = Field(ge=0)
    text: str
    bbox: tuple[float, float, float, float]
    font: str | None = None
    size: float | None = Field(default=None, ge=0.0)
    flags: int | None = None


class EvidenceBlock(BaseModel):
    page: int = Field(ge=1)
    block_index: int = Field(ge=0)
    text: str
    bbox: tuple[float, float, float, float]
    font_sizes: list[float] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    spans: list[EvidenceSpan] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_span_sequence(self) -> EvidenceBlock:
        if any(span.span_index != index for index, span in enumerate(self.spans)):
            raise ValueError("span_index values must match their position in the block")
        if any(
            current.line_index < previous.line_index
            for previous, current in zip(self.spans, self.spans[1:])
        ):
            raise ValueError("span line indices must be in source order")
        return self


class RowEvidence(BaseModel):
    candidate_pages: list[int] = Field(default_factory=list)
    best_match_page: int | None = None
    best_match_block_index: int | None = None
    best_match_text: str | None = None
    best_match_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    surrounding_blocks: list[EvidenceBlock] = Field(default_factory=list)
    visual_required_reasons: list[str] = Field(default_factory=list)


class ReviewPacketRow(BaseModel):
    node_id: str = Field(min_length=1)
    locked: dict[str, Any]
    locked_sha256: str = Field(min_length=64, max_length=64)
    evidence: RowEvidence


class BatchScope(BaseModel):
    work_key: str = Field(min_length=1)
    unit_field: str = Field(min_length=1)
    authorized_units: list[str | int] = Field(min_length=1)
    expected_counts: dict[str, int]
    expected_total: int = Field(ge=1)
    pdf_page_start: int | None = Field(default=None, ge=1)
    pdf_page_end: int | None = Field(default=None, ge=1)
    reverse_coverage_required: bool = True
    classification_required: bool = False

    @model_validator(mode="after")
    def validate_scope(self) -> "BatchScope":
        unit_keys = [str(unit) for unit in self.authorized_units]
        if len(unit_keys) != len(set(unit_keys)):
            raise ValueError("authorized_units contains duplicates")
        if set(self.expected_counts) != set(unit_keys):
            raise ValueError("expected_counts keys must exactly match authorized_units")
        if any(count < 0 for count in self.expected_counts.values()):
            raise ValueError("expected_counts must be non-negative")
        if sum(self.expected_counts.values()) != self.expected_total:
            raise ValueError("expected_counts do not sum to expected_total")
        if (self.pdf_page_start is None) != (self.pdf_page_end is None):
            raise ValueError("physical scope requires both pdf_page_start and pdf_page_end")
        if (
            self.pdf_page_start is not None
            and self.pdf_page_end is not None
            and self.pdf_page_end < self.pdf_page_start
        ):
            raise ValueError("pdf_page_end precedes pdf_page_start")
        if self.reverse_coverage_required and self.pdf_page_start is None:
            raise ValueError("reverse coverage requires an explicit physical PDF scope")
        return self


class ReviewPacket(BaseModel):
    schema_version: str = SCHEMA_VERSION
    batch_id: str = Field(min_length=1)
    work_key: str | None = None
    manifest_sha256: str = Field(min_length=64, max_length=64)
    scope_sha256: str | None = None
    scope_evidence_sha256: str | None = None
    scope: BatchScope | None = None
    source: SourceIdentity
    evidence_pages: list[int] = Field(default_factory=list)
    scope_blocks: list[EvidenceBlock] = Field(default_factory=list)
    point_locator_only: bool = True
    allowed_dispositions: list[str] = Field(default_factory=list)
    rows: list[ReviewPacketRow]


class BatchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    disposition: str | None = None
    resolution_status: str | None = None
    final_classification: str | None = None
    candidate_pdf_page: int | None = Field(default=None, ge=1)
    canonical_pdf_page: int | None = Field(default=None, ge=1)
    heading_observed: str | None = None
    folio_observed: int | None = None
    evidence_method: str | None = None
    page_end: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    canonical_identity_text: str | None = None
    canonical_parent_observation_id: str | None = None
    merge_target_observation_id: str | None = None
    notes: str | None = None



class SourceAugmentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    augmentation_observation_id: str = Field(min_length=1)
    unit_value: str | int
    pdf_page: int = Field(ge=1)
    physical_block_indices: list[int] = Field(min_length=1)
    span_refs: list[tuple[int, int]] = Field(default_factory=list)
    exact_source_text: str = Field(min_length=1)
    extraction_raw_text: str | None = None
    font_span_evidence: dict[str, Any] = Field(default_factory=dict)
    bbox: tuple[float, float, float, float]
    source_id: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    source_observed: bool = True
    final_classification: str
    canonical_parent_observation_id: str | None = None
    page_end: int | None = Field(default=None, ge=1)
    notes: str | None = None


class DecisionSet(BaseModel):
    schema_version: str = SCHEMA_VERSION
    batch_id: str = Field(min_length=1)
    work_key: str | None = None
    manifest_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    scope_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    scope_evidence_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    decisions: list[BatchDecision]
    augmentations: list[SourceAugmentation] = Field(default_factory=list)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _scope_evidence_sha256(
    source: SourceIdentity,
    scope: BatchScope,
    blocks: list[EvidenceBlock],
) -> str:
    return canonical_sha256({
        "source": source.model_dump(mode="json"),
        "scope": scope.model_dump(mode="json"),
        "blocks": [block.model_dump(mode="json") for block in blocks],
    })


def load_manifest_rows(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        metadata: dict[str, Any] = {}
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        metadata = {key: value for key, value in payload.items() if key != "rows"}
        rows = payload["rows"]
    else:
        raise ValueError("manifest must be a JSON list or an object with a rows list")

    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("every manifest row must be a JSON object")
    node_ids = [str(row.get("node_id") or row.get("observation_id") or "") for row in rows]
    if any(not node_id for node_id in node_ids):
        raise ValueError("every manifest row requires node_id or observation_id")
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("manifest contains duplicate node IDs")
    return metadata, rows


def validate_manifest_scope(
    metadata: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    required: bool = False,
) -> BatchScope | None:
    raw_scope = metadata.get("scope")
    if raw_scope is None:
        if required:
            raise ValueError("manifest requires a machine-readable scope lock")
        return None
    scope = BatchScope.model_validate(raw_scope)
    counts = {str(unit): 0 for unit in scope.authorized_units}
    for row in rows:
        value = row.get(scope.unit_field)
        key = str(value)
        if key not in counts:
            raise ValueError(
                f"manifest row is outside authorized scope: "
                f"{scope.unit_field}={value!r}"
            )
        counts[key] += 1
    if counts != scope.expected_counts:
        raise ValueError(
            f"scope population mismatch: expected={scope.expected_counts}; actual={counts}"
        )
    if len(rows) != scope.expected_total:
        raise ValueError(
            f"scope total mismatch: expected={scope.expected_total}; actual={len(rows)}"
        )
    return scope


def _row_id(row: dict[str, Any]) -> str:
    return str(row.get("node_id") or row.get("observation_id"))


def _expected_heading(row: dict[str, Any]) -> str:
    for field in _DEFAULT_HEADING_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _add_page(pages: list[int], value: Any) -> None:
    if isinstance(value, int) and value > 0 and value not in pages:
        pages.append(value)


def candidate_pages(row: dict[str, Any]) -> list[int]:
    pages: list[int] = []
    for field in ("selected_pdf_page", "candidate_pdf_page", "canonical_pdf_page"):
        _add_page(pages, row.get(field))

    for field in ("folio_target_pages", "candidate_pages", "old_candidate_pages"):
        values = row.get(field)
        if isinstance(values, list):
            for value in values:
                _add_page(pages, value)

    locator = row.get("old_locator")
    if isinstance(locator, dict):
        split_pages = locator.get("split_part_pdf_pages")
        if isinstance(split_pages, list):
            for item in split_pages:
                if isinstance(item, dict):
                    _add_page(pages, item.get("pdf_page"))
    return pages


def evidence_pages_for_rows(
    rows: list[dict[str, Any]],
    *,
    neighbor_pages: int = 1,
    page_count: int | None = None,
) -> list[int]:
    if neighbor_pages < 0:
        raise ValueError("neighbor_pages must be >= 0")

    required = sorted({page for row in rows for page in candidate_pages(row)})
    if page_count is not None:
        outside = [page for page in required if page < 1 or page > page_count]
        if outside:
            raise ValueError(
                f"candidate pages are outside the PDF: {outside}; page_count={page_count}"
            )

    pages: set[int] = set()
    for page in required:
        start = max(1, page - neighbor_pages)
        end = page + neighbor_pages
        if page_count is not None:
            end = min(page_count, end)
        pages.update(range(start, end + 1))
    return sorted(pages)


def evidence_pages_for_scope(
    rows: list[dict[str, Any]],
    *,
    scope: BatchScope | None,
    neighbor_pages: int = 1,
    page_count: int | None = None,
) -> list[int]:
    pages = set(
        evidence_pages_for_rows(
            rows,
            neighbor_pages=neighbor_pages,
            page_count=page_count,
        )
    )
    if scope is None or not scope.reverse_coverage_required:
        return sorted(pages)

    assert scope.pdf_page_start is not None
    assert scope.pdf_page_end is not None
    if page_count is not None and scope.pdf_page_end > page_count:
        raise ValueError(
            f"physical scope exceeds the PDF: "
            f"{scope.pdf_page_start}-{scope.pdf_page_end}; page_count={page_count}"
        )
    candidate = {page for row in rows for page in candidate_pages(row)}
    outside = sorted(
        page
        for page in candidate
        if page < scope.pdf_page_start or page > scope.pdf_page_end
    )
    if outside:
        raise ValueError(
            f"candidate pages escape the physical scope: {outside}; "
            f"scope={scope.pdf_page_start}-{scope.pdf_page_end}"
        )
    pages.update(range(scope.pdf_page_start, scope.pdf_page_end + 1))
    return sorted(pages)


def _best_evidence(
    row: dict[str, Any],
    blocks_by_page: dict[int, list[EvidenceBlock]],
) -> RowEvidence:
    pages = candidate_pages(row)
    expected = _normalize(_expected_heading(row))
    best: tuple[float, EvidenceBlock] | None = None

    for page in pages:
        for block in blocks_by_page.get(page, []):
            ratio = SequenceMatcher(None, expected, _normalize(block.text)).ratio() if expected else 0.0
            if best is None or ratio > best[0]:
                best = (ratio, block)

    surrounding: list[EvidenceBlock] = []
    if best is not None:
        matched = best[1]
        page_blocks = blocks_by_page.get(matched.page, [])
        pos = next(
            (i for i, block in enumerate(page_blocks) if block.block_index == matched.block_index),
            None,
        )
        if pos is not None:
            surrounding = page_blocks[max(0, pos - 1) : pos + 2]

    reasons: list[str] = []
    if not pages:
        reasons.append("NO_CANDIDATE_PAGE")
    if len(pages) > 1:
        reasons.append("MULTIPLE_CANDIDATE_PAGES")
    if best is None:
        reasons.append("NO_TEXT_BLOCK_MATCH")
    elif best[0] < 0.92:
        reasons.append("LOW_TEXT_MATCH")
    printed = row.get("printed_page") or row.get("printed_page_label")
    if printed is not None and not row.get("folio_target_pages"):
        reasons.append("FOLIO_NOT_DETERMINISTIC")

    return RowEvidence(
        candidate_pages=pages,
        best_match_page=best[1].page if best else None,
        best_match_block_index=best[1].block_index if best else None,
        best_match_text=best[1].text if best else None,
        best_match_ratio=round(best[0], 6) if best else None,
        surrounding_blocks=surrounding,
        visual_required_reasons=sorted(set(reasons)),
    )


def build_review_packet(
    *,
    batch_id: str,
    manifest_sha256: str,
    rows: list[dict[str, Any]],
    source: SourceIdentity,
    blocks: list[EvidenceBlock],
    point_locator_only: bool = True,
    allowed_dispositions: list[str] | None = None,
    evidence_pages: list[int] | None = None,
    scope: BatchScope | None = None,
) -> ReviewPacket:
    by_page: dict[int, list[EvidenceBlock]] = {}
    for block in blocks:
        by_page.setdefault(block.page, []).append(block)

    packet_rows = [
        ReviewPacketRow(
            node_id=_row_id(row),
            locked=row,
            locked_sha256=canonical_sha256(row),
            evidence=_best_evidence(row, by_page),
        )
        for row in rows
    ]
    scope_sha256 = (
        canonical_sha256(scope.model_dump(mode="json")) if scope is not None else None
    )
    scope_blocks = (
        sorted(blocks, key=lambda block: (block.page, block.block_index))
        if scope is not None
        else []
    )
    scope_evidence_sha256 = (
        _scope_evidence_sha256(source, scope, scope_blocks)
        if scope is not None
        else None
    )
    return ReviewPacket(
        batch_id=batch_id,
        work_key=scope.work_key if scope is not None else None,
        manifest_sha256=manifest_sha256,
        scope_sha256=scope_sha256,
        scope_evidence_sha256=scope_evidence_sha256,
        scope=scope,
        source=source,
        evidence_pages=evidence_pages or sorted(by_page),
        scope_blocks=scope_blocks,
        point_locator_only=point_locator_only,
        allowed_dispositions=allowed_dispositions or [],
        rows=packet_rows,
    )


def _extract_page_blocks(page: Any, page_number: int) -> list[EvidenceBlock]:
    raw_page = page.get_text("dict")
    blocks: list[EvidenceBlock] = []
    # Keep the PDF's original block index; Source Map locators use this physical identity.
    for block_index, raw_block in enumerate(raw_page.get("blocks", [])):
        if raw_block.get("type") != 0:
            continue
        lines = raw_block.get("lines") or []
        spans = [span for line in lines for span in (line.get("spans") or [])]
        text = "\n".join(
            "".join(str(span.get("text") or "") for span in (line.get("spans") or []))
            for line in lines
        ).strip()
        if not text:
            continue
        bbox = raw_block.get("bbox") or (0.0, 0.0, 0.0, 0.0)
        evidence_spans: list[EvidenceSpan] = []
        span_index = 0
        for line_index, line in enumerate(lines):
            for span in line.get("spans") or []:
                evidence_spans.append(
                    EvidenceSpan(
                        line_index=line_index,
                        span_index=span_index,
                        text=str(span.get("text") or ""),
                        bbox=tuple(float(value) for value in (span.get("bbox") or bbox)),
                        font=str(span.get("font")) if span.get("font") else None,
                        size=(
                            float(span["size"])
                            if span.get("size") is not None
                            else None
                        ),
                        flags=int(span["flags"]) if span.get("flags") is not None else None,
                    )
                )
                span_index += 1
        blocks.append(
            EvidenceBlock(
                page=page_number,
                block_index=block_index,
                text=text,
                bbox=tuple(float(value) for value in bbox),
                font_sizes=sorted(
                    {round(float(span.get("size") or 0.0), 3) for span in spans}
                ),
                fonts=sorted(
                    {str(span.get("font")) for span in spans if span.get("font")}
                ),
                spans=evidence_spans,
            )
        )
    return blocks


def extract_pdf_blocks_cached(
    pdf_path: Path,
    cache_dir: Path,
    *,
    pages: list[int] | None = None,
) -> tuple[str, int, list[EvidenceBlock]]:
    digest = sha256_file(pdf_path)

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PDF block extraction requires the pdf-native extra: pip install -e '.[pdf-native]'"
        ) from exc

    document = fitz.open(str(pdf_path))
    try:
        page_count = len(document)
        requested_pages = (
            list(range(1, page_count + 1))
            if pages is None
            else sorted(set(pages))
        )
        outside = [page for page in requested_pages if page < 1 or page > page_count]
        if outside:
            raise ValueError(
                f"requested evidence pages are outside the PDF: {outside}; page_count={page_count}"
            )

        source_cache = cache_dir / digest
        pages_dir = source_cache / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "cache_version": BLOCK_CACHE_VERSION,
            "content_sha256": digest,
            "size_bytes": pdf_path.stat().st_size,
            "page_count": page_count,
        }
        (source_cache / "source.json").write_bytes(canonical_json_bytes(metadata))

        blocks: list[EvidenceBlock] = []
        for page_number in requested_pages:
            page_cache = pages_dir / f"p{page_number:04d}.json"
            if page_cache.exists():
                payload = json.loads(page_cache.read_text(encoding="utf-8"))
                if (
                    payload.get("cache_version") != BLOCK_CACHE_VERSION
                    or payload.get("content_sha256") != digest
                    or payload.get("page") != page_number
                ):
                    page_cache.unlink()
                    payload = None
            else:
                payload = None

            if payload is None:
                page_blocks = _extract_page_blocks(document[page_number - 1], page_number)
                payload = {
                    "cache_version": BLOCK_CACHE_VERSION,
                    "content_sha256": digest,
                    "page": page_number,
                    "blocks": [block.model_dump(mode="json") for block in page_blocks],
                }
                page_cache.write_bytes(canonical_json_bytes(payload))
            else:
                page_blocks = [
                    EvidenceBlock.model_validate(item) for item in payload.get("blocks", [])
                ]
            blocks.extend(page_blocks)

        return digest, page_count, blocks
    finally:
        document.close()

def prepare_from_pdf(
    *,
    manifest_path: Path,
    pdf_path: Path,
    output_path: Path,
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
    require_scope: bool = True,
) -> ReviewPacket:
    raw_manifest = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(raw_manifest).hexdigest()
    metadata, rows = load_manifest_rows(manifest_path)
    scope = validate_manifest_scope(metadata, rows, required=require_scope)

    if expected_size is not None and pdf_path.stat().st_size != expected_size:
        raise ValueError(
            f"source size mismatch: expected {expected_size}, got {pdf_path.stat().st_size}"
        )

    page_count_hint = native_pdf_page_count(pdf_path)
    evidence_pages = evidence_pages_for_scope(
        rows,
        scope=scope,
        neighbor_pages=1,
        page_count=page_count_hint,
    )
    digest, page_count, blocks = extract_pdf_blocks_cached(
        pdf_path,
        cache_dir,
        pages=evidence_pages,
    )
    if page_count != page_count_hint:
        raise ValueError(
            f"PDF page count changed during prepare: {page_count_hint} -> {page_count}"
        )
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(
            f"source SHA-256 mismatch: expected {expected_sha256}, got {digest}"
        )

    source = SourceIdentity(
        logical_source_id=logical_source_id,
        source_id=source_id,
        provider_file_id=provider_file_id,
        content_sha256=digest,
        size_bytes=pdf_path.stat().st_size,
        page_count=page_count,
        binding_state=binding_state,
    )
    packet = build_review_packet(
        batch_id=batch_id,
        manifest_sha256=manifest_sha256,
        rows=rows,
        source=source,
        blocks=blocks,
        point_locator_only=point_locator_only,
        allowed_dispositions=allowed_dispositions,
        evidence_pages=evidence_pages,
        scope=scope,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(packet.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return packet


def _is_gap(binding_state: str) -> bool:
    upper = binding_state.upper()
    return any(marker in upper for marker in _GAP_MARKERS)


def _claims_verified(decision: BatchDecision) -> bool:
    values = (
        decision.disposition,
        decision.resolution_status,
        decision.final_classification,
    )
    return any(value and "VERIFIED" in value.upper() for value in values)


def validate_decisions(packet: ReviewPacket, decisions: DecisionSet) -> list[str]:
    errors: list[str] = []
    if decisions.batch_id != packet.batch_id:
        errors.append(
            f"batch_id mismatch: packet={packet.batch_id!r}, decisions={decisions.batch_id!r}"
        )
    if packet.scope is not None:
        if decisions.work_key != packet.work_key:
            errors.append(
                f"work_key mismatch: packet={packet.work_key!r}, decisions={decisions.work_key!r}"
            )
        if decisions.manifest_sha256 != packet.manifest_sha256:
            errors.append("decision manifest_sha256 does not match the locked packet")
        if decisions.scope_sha256 != packet.scope_sha256:
            errors.append("decision scope_sha256 does not match the locked packet")
        expected_evidence_sha256 = _scope_evidence_sha256(
            packet.source, packet.scope, packet.scope_blocks
        )
        if packet.scope_evidence_sha256 != expected_evidence_sha256:
            errors.append("packet scope evidence digest mismatch")
        if (
            decisions.augmentations
            and decisions.scope_evidence_sha256 != packet.scope_evidence_sha256
        ):
            errors.append("augmentation decisions are not bound to packet scope evidence")

    packet_ids = [row.node_id for row in packet.rows]
    decision_ids = [decision.node_id for decision in decisions.decisions]
    if len(decision_ids) != len(set(decision_ids)):
        errors.append("decisions contain duplicate node IDs")
    if decision_ids != packet_ids:
        missing = [node_id for node_id in packet_ids if node_id not in set(decision_ids)]
        extra = [node_id for node_id in decision_ids if node_id not in set(packet_ids)]
        errors.append(
            "decision node order/set does not exactly match packet"
            f"; missing={missing}; extra={extra}"
        )

    for row in packet.rows:
        if canonical_sha256(row.locked) != row.locked_sha256:
            errors.append(f"{row.node_id}: locked row hash mismatch")

    allowed = set(packet.allowed_dispositions)
    for decision in decisions.decisions:
        if allowed and decision.disposition not in allowed:
            errors.append(
                f"{decision.node_id}: disposition {decision.disposition!r} is not allowed"
            )
        if packet.point_locator_only and decision.page_end is not None:
            errors.append(f"{decision.node_id}: page_end must be null for point locators")
        if _is_gap(packet.source.binding_state) and _claims_verified(decision):
            errors.append(
                f"{decision.node_id}: VERIFIED state forbidden while source binding is "
                f"{packet.source.binding_state}"
            )
        if (
            decision.canonical_pdf_page is not None
            and packet.source.binding_state.upper() not in _EXACT_BINDINGS
        ):
            errors.append(
                f"{decision.node_id}: canonical_pdf_page requires exact canonical source binding"
            )
        page = decision.canonical_pdf_page or decision.candidate_pdf_page
        if (
            page is not None
            and packet.source.page_count is not None
            and page > packet.source.page_count
        ):
            errors.append(
                f"{decision.node_id}: PDF page {page} exceeds source page count "
                f"{packet.source.page_count}"
            )

    has_structural_decisions = any(
        decision.final_classification is not None
        for decision in decisions.decisions
    ) or bool(decisions.augmentations)
    if packet.scope is not None and (
        packet.scope.classification_required or has_structural_decisions
    ):
        required_classes = {"REQUIRED_SECTION", "REQUIRED_SUBSECTION"}
        classification_by_id = {
            decision.node_id: decision.final_classification
            for decision in decisions.decisions
        }
        parent_by_id = {
            decision.node_id: decision.canonical_parent_observation_id
            for decision in decisions.decisions
        }
        unit_by_id = {
            row.node_id: str(row.locked.get(packet.scope.unit_field))
            for row in packet.rows
        }

        packet_id_set = set(packet_ids)
        augmentation_ids = [
            augmentation.augmentation_observation_id
            for augmentation in decisions.augmentations
        ]
        if len(augmentation_ids) != len(set(augmentation_ids)):
            errors.append("augmentations contain duplicate observation IDs")
        collisions = sorted(packet_id_set.intersection(augmentation_ids))
        if collisions:
            errors.append(f"augmentation IDs collide with frozen rows: {collisions}")

        for augmentation in decisions.augmentations:
            augmentation_id = augmentation.augmentation_observation_id
            classification_by_id[augmentation_id] = augmentation.final_classification
            parent_by_id[augmentation_id] = augmentation.canonical_parent_observation_id
            unit_by_id[augmentation_id] = str(augmentation.unit_value)
            if unit_by_id[augmentation_id] not in {
                str(unit) for unit in packet.scope.authorized_units
            }:
                errors.append(
                    f"{augmentation_id}: augmentation is outside authorized scope"
                )
            if (
                packet.scope.pdf_page_start is not None
                and packet.scope.pdf_page_end is not None
                and not (
                    packet.scope.pdf_page_start
                    <= augmentation.pdf_page
                    <= packet.scope.pdf_page_end
                )
            ):
                errors.append(
                    f"{augmentation_id}: augmentation page is outside physical scope"
                )
            if augmentation.source_id != packet.source.source_id:
                errors.append(f"{augmentation_id}: augmentation source_id mismatch")
            if augmentation.source_sha256 != packet.source.content_sha256:
                errors.append(f"{augmentation_id}: augmentation source SHA mismatch")
            if not augmentation.source_observed:
                errors.append(
                    f"{augmentation_id}: augmentation must be source_observed=true"
                )
            if len(augmentation.physical_block_indices) != len(
                set(augmentation.physical_block_indices)
            ):
                errors.append(f"{augmentation_id}: physical block indices contain duplicates")
            block_by_key = {
                (block.page, block.block_index): block
                for block in packet.scope_blocks
            }
            if len(block_by_key) != len(packet.scope_blocks):
                errors.append("packet scope evidence contains duplicate page/block identities")
            selected_blocks = [
                block_by_key.get((augmentation.pdf_page, block_index))
                for block_index in augmentation.physical_block_indices
            ]
            if any(block is None for block in selected_blocks):
                errors.append(
                    f"{augmentation_id}: physical source block is missing from packet evidence"
                )
            else:
                if augmentation.span_refs:
                    if len(augmentation.span_refs) != len(set(augmentation.span_refs)):
                        errors.append(f"{augmentation_id}: span references contain duplicates")
                    selected_block_ids = set(augmentation.physical_block_indices)
                    refs = []
                    for block_index, span_index in augmentation.span_refs:
                        if block_index not in selected_block_ids:
                            errors.append(
                                f"{augmentation_id}: span reference is outside selected blocks"
                            )
                            continue
                        block = block_by_key.get((augmentation.pdf_page, block_index))
                        span = next(
                            (
                                item for item in (block.spans if block is not None else [])
                                if item.span_index == span_index
                            ),
                            None,
                        )
                        if span is None:
                            errors.append(
                                f"{augmentation_id}: source span is missing from packet evidence"
                            )
                            continue
                        refs.append((block_index, span))
                    if len(refs) == len(augmentation.span_refs):
                        order = [
                            (block_index, span.line_index, span.span_index)
                            for block_index, span in refs
                        ]
                        if order != sorted(order):
                            errors.append(
                                f"{augmentation_id}: span references are not in source order"
                            )
                        for (previous_block, previous_span), (block_index, span) in zip(
                            refs, refs[1:]
                        ):
                            previous_block_evidence = block_by_key.get(
                                (augmentation.pdf_page, previous_block)
                            )
                            current_block_evidence = block_by_key.get(
                                (augmentation.pdf_page, block_index)
                            )
                            previous_position = next(
                                (
                                    index
                                    for index, item in enumerate(
                                        previous_block_evidence.spans
                                        if previous_block_evidence is not None
                                        else []
                                    )
                                    if item is previous_span
                                ),
                                None,
                            )
                            current_position = next(
                                (
                                    index
                                    for index, item in enumerate(
                                        current_block_evidence.spans
                                        if current_block_evidence is not None
                                        else []
                                    )
                                    if item is span
                                ),
                                None,
                            )
                            if block_index == previous_block:
                                contiguous = current_position == previous_position + 1
                            else:
                                contiguous = (
                                    block_index == previous_block + 1
                                    and previous_block_evidence is not None
                                    and current_block_evidence is not None
                                    and previous_position
                                    == len(previous_block_evidence.spans) - 1
                                    and current_position == 0
                                )
                            if not contiguous:
                                errors.append(
                                    f"{augmentation_id}: span references are not contiguous source spans"
                                )
                                break
                        line_text: list[str] = []
                        last_line: tuple[int, int] | None = None
                        for block_index, span in refs:
                            line = (block_index, span.line_index)
                            if line != last_line:
                                line_text.append(span.text)
                                last_line = line
                            else:
                                line_text[-1] += span.text
                        observed_text = " ".join(line_text)
                        if observed_text != augmentation.exact_source_text:
                            errors.append(
                                f"{augmentation_id}: exact_source_text does not match packet spans"
                            )
                        observed_bbox = (
                            min(span.bbox[0] for _, span in refs),
                            min(span.bbox[1] for _, span in refs),
                            max(span.bbox[2] for _, span in refs),
                            max(span.bbox[3] for _, span in refs),
                        )
                    else:
                        observed_bbox = augmentation.bbox
                else:
                    observed_text = "\n".join(
                        block.text for block in selected_blocks if block is not None
                    )
                    if observed_text != augmentation.exact_source_text:
                        errors.append(
                            f"{augmentation_id}: exact_source_text does not match packet blocks"
                        )
                    observed_bbox = (
                        min(block.bbox[0] for block in selected_blocks if block is not None),
                        min(block.bbox[1] for block in selected_blocks if block is not None),
                        max(block.bbox[2] for block in selected_blocks if block is not None),
                        max(block.bbox[3] for block in selected_blocks if block is not None),
                    )
                if not all(
                    math.isclose(actual, expected, abs_tol=0.01)
                    for actual, expected in zip(augmentation.bbox, observed_bbox)
                ):
                    errors.append(
                        f"{augmentation_id}: bbox does not match packet source blocks"
                    )
            if augmentation.page_end is not None:
                errors.append(f"{augmentation_id}: augmentation page_end must be null")
            if augmentation.final_classification not in required_classes:
                errors.append(
                    f"{augmentation_id}: augmentation must be a required structural identity"
                )

        all_ids = set(classification_by_id)
        for decision in decisions.decisions:
            classification = decision.final_classification
            if decision.resolution_status == "VERIFIED" and not classification:
                errors.append(
                    f"{decision.node_id}: VERIFIED classification row has no final_classification"
                )
            if classification == "REQUIRED_SUBSECTION":
                parent = decision.canonical_parent_observation_id
                if not parent or parent not in all_ids:
                    errors.append(
                        f"{decision.node_id}: REQUIRED_SUBSECTION has missing parent"
                    )
                elif classification_by_id.get(parent) not in required_classes:
                    errors.append(
                        f"{decision.node_id}: REQUIRED_SUBSECTION parent is not structural"
                    )
                elif unit_by_id.get(parent) != unit_by_id.get(decision.node_id):
                    errors.append(
                        f"{decision.node_id}: REQUIRED_SUBSECTION parent crosses scope unit"
                    )
            if classification == "MERGE_WITH_ADJACENT_SOURCE_IDENTITY":
                target = decision.merge_target_observation_id
                if not target or target not in all_ids:
                    errors.append(f"{decision.node_id}: MERGE has missing target")
                elif classification_by_id.get(target) == "MERGE_WITH_ADJACENT_SOURCE_IDENTITY":
                    errors.append(f"{decision.node_id}: MERGE cannot target another MERGE")
                elif unit_by_id.get(target) != unit_by_id.get(decision.node_id):
                    errors.append(f"{decision.node_id}: MERGE target crosses scope unit")

        for augmentation in decisions.augmentations:
            if augmentation.final_classification == "REQUIRED_SUBSECTION":
                parent = augmentation.canonical_parent_observation_id
                augmentation_id = augmentation.augmentation_observation_id
                if not parent or parent not in all_ids:
                    errors.append(
                        f"{augmentation_id}: REQUIRED_SUBSECTION augmentation has missing parent"
                    )
                elif classification_by_id.get(parent) not in required_classes:
                    errors.append(
                        f"{augmentation_id}: augmentation parent is not structural"
                    )
                elif unit_by_id.get(parent) != unit_by_id.get(augmentation_id):
                    errors.append(
                        f"{augmentation_id}: augmentation parent crosses scope unit"
                    )

        for node_id in all_ids:
            seen: set[str] = set()
            cursor = node_id
            while cursor in all_ids:
                if cursor in seen:
                    errors.append(f"{node_id}: structural parent cycle detected")
                    break
                seen.add(cursor)
                parent = parent_by_id.get(cursor)
                if not parent:
                    break
                cursor = parent

    return errors


def load_packet(path: Path) -> ReviewPacket:
    return ReviewPacket.model_validate_json(path.read_text(encoding="utf-8"))


def load_decisions(path: Path) -> DecisionSet:
    return DecisionSet.model_validate_json(path.read_text(encoding="utf-8"))
