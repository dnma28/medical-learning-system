from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .sources import sha256_file


SCHEMA_VERSION = "1.0.0"
BLOCK_CACHE_VERSION = "blocks-v1"
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


class EvidenceBlock(BaseModel):
    page: int = Field(ge=1)
    block_index: int = Field(ge=0)
    text: str
    bbox: tuple[float, float, float, float]
    font_sizes: list[float] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)


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


class ReviewPacket(BaseModel):
    schema_version: str = SCHEMA_VERSION
    batch_id: str = Field(min_length=1)
    manifest_sha256: str = Field(min_length=64, max_length=64)
    source: SourceIdentity
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


class DecisionSet(BaseModel):
    schema_version: str = SCHEMA_VERSION
    batch_id: str = Field(min_length=1)
    decisions: list[BatchDecision]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


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


def candidate_pages(row: dict[str, Any], *, limit: int = 8) -> list[int]:
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
    return pages[:limit]


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
    return ReviewPacket(
        batch_id=batch_id,
        manifest_sha256=manifest_sha256,
        source=source,
        point_locator_only=point_locator_only,
        allowed_dispositions=allowed_dispositions or [],
        rows=packet_rows,
    )


def extract_pdf_blocks_cached(
    pdf_path: Path,
    cache_dir: Path,
) -> tuple[str, int, list[EvidenceBlock]]:
    digest = sha256_file(pdf_path)
    cache_path = cache_dir / digest / f"{BLOCK_CACHE_VERSION}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        return digest, int(payload["page_count"]), [
            EvidenceBlock.model_validate(item) for item in payload["blocks"]
        ]

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PDF block extraction requires the pdf-native extra: pip install -e '.[pdf-native]'"
        ) from exc

    document = fitz.open(str(pdf_path))
    blocks: list[EvidenceBlock] = []
    global_index = 0
    for page_index in range(len(document)):
        page = document[page_index]
        raw_page = page.get_text("dict", sort=True)
        for raw_block in raw_page.get("blocks", []):
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
            blocks.append(
                EvidenceBlock(
                    page=page_index + 1,
                    block_index=global_index,
                    text=text,
                    bbox=tuple(float(value) for value in bbox),
                    font_sizes=sorted(
                        {round(float(span.get("size") or 0.0), 3) for span in spans}
                    ),
                    fonts=sorted(
                        {str(span.get("font")) for span in spans if span.get("font")}
                    ),
                )
            )
            global_index += 1

    payload = {
        "cache_version": BLOCK_CACHE_VERSION,
        "content_sha256": digest,
        "page_count": len(document),
        "blocks": [block.model_dump(mode="json") for block in blocks],
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(canonical_json_bytes(payload))
    return digest, len(document), blocks


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
) -> ReviewPacket:
    raw_manifest = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(raw_manifest).hexdigest()
    _, rows = load_manifest_rows(manifest_path)

    if expected_size is not None and pdf_path.stat().st_size != expected_size:
        raise ValueError(
            f"source size mismatch: expected {expected_size}, got {pdf_path.stat().st_size}"
        )

    digest, page_count, blocks = extract_pdf_blocks_cached(pdf_path, cache_dir)
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
    return errors


def load_packet(path: Path) -> ReviewPacket:
    return ReviewPacket.model_validate_json(path.read_text(encoding="utf-8"))


def load_decisions(path: Path) -> DecisionSet:
    return DecisionSet.model_validate_json(path.read_text(encoding="utf-8"))
