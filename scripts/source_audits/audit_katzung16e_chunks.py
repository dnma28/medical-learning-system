#!/usr/bin/env python3
from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz

LOGICAL_SOURCE_ID = "katzung-basic-clinical-pharmacology"

# Exact live registry snapshot, refreshed 2026-09-27.
# These are the 20 canonical registered chunks. The audit fails closed if any
# byte fingerprint differs from the registry.
SOURCE_MANIFEST = [
    (1, "1QyIOGcSYdr2mJFwosd8sWH9Z9TXCSxUi", 10310044, "47148b67d513f9a976ba527cf0e9407232a8bce762ac2a9382250d9d539e18b6"),
    (2, "1sKChgBpK6pUgCzvDAflRO75_wEhUVlrl", 3126560, "4040525cc909eea2e7c42c75dffcddef0bd901f2aa19fdfc8abb0b015f99a0af"),
    (3, "1CZE3MPkNo3NMlOIplATL1AV_iQ8sm5Cf", 12791129, "0532c0fd7271b1208b63e0bbff41435060a98683e66d1918b7a3f08e8e1ed08f"),
    (4, "1uerpAYyxj6m8Uieh8pPNU8yuAzPGI50E", 15059132, "3c5c95bb46d204586277f6924ba8d41e336078ba108ac6cb657727984bb6d1f3"),
    (5, "1IwjWFwTYM_Pia_VaWlVH3-u1l3CVN2yo", 5241596, "419d19bc8bb94fb7bd749a6e841a6f29ebe4fd3e237bf45cdb43b3cd8f666571"),
    (6, "1sieg45UxC4hEKvCDB2Q-_AI1adzxibvu", 12001683, "07b970cce72805f400f070b072a49da06628b4022e2b7812f4da0fc897c5d0ce"),
    (7, "1HlbzZUdPSgvS6m_jE2Gnykh1eUbiBV-n", 12687855, "c830b116ae17b4d2d32d0f3f5ba7f1f44dfef21e4d7bd0749fd9672d8ad307fc"),
    (8, "1PWhpgzqbVmBw5PWN19vfCu-hofyb7gE9", 12967924, "4c585408f054214d63df11687e6bb8605659d5debdaf88e7a7f7691ede144121"),
    (9, "1kRIsfuzrGe_TGuXfrCApn6CCjx8Nq9LI", 12935560, "d7a0eceedd4a55eb1aec51cb85602fb924f6cc2c7232706270b1493d7762a407"),
    (10, "1ngbQCDGUAZN9ro1OGTChQ2pPIn_eM74N", 3818273, "910488accc8d712f861b5c14f888fa8084ad8dc66509cf14a71417fe75a7ec48"),
    (11, "1cJQs67kwLTCKpcwuK_a6NgucoqOmw0YW", 4341757, "f337fbfed9f2607a22fcc1bac3238387cd4c0289b59f3e96c7d4201c502814a9"),
    (12, "1v84_JctRof43o651jNTdcCPgTeXpKK6w", 4125398, "313bb90dd4c3d7b5a1a6159988519896cb074ccb08e5dc617cd5b1e1476bdb2b"),
    (13, "17-snt8Ccc1CiNmsEpRUz2df7HlPrnuAw", 2702626, "7fc7f41a4326ed26d27a23094038228e03ccf7f6dbd0baadece98a0b2cef5712"),
    (14, "11GkzDcuQTs4R7QZvkYan7ZTXGCiZK7vD", 4088775, "9dd38d37b4bc2d4a45d6f2037c86b00ecabcc9791bc93f5f1545a712276fef01"),
    (15, "1y-0kdZED1l8aF2Z4ZvUhIFlec-q4xdL0", 12823048, "bd53797c76ae30889708e3504d74fdf4cd3f615505cde78feb43939dad2a1665"),
    (16, "1hzoW91Ug6eKGDsrfMzduPV-rVb6_jQ0t", 2709328, "9f7f40168f99b4e073134bdc03528b88145e3abdbfc3fa562bb4cc1e8f8dad50"),
    (17, "1sCfQtBgbXokW-FVhceytvPlVfnI44Nej", 4917677, "2758be0d06457fcee2606c17a34f6bff01b46b5351c8dca07b6dde4ba9319dae"),
    (18, "1oBuGnTloKsmc4xMKW9sSNV58JQpIqzu1", 2935373, "9957959d02cdc328f9979f9627d6501761da1ae121b902cb0df1eafbc3240371"),
    (19, "1xhB20OVorkmf_r1q1O-kmyUmHGIF_cBD", 3157478, "c6dde14b0259b79c887596834f0dd19840e58e285f04ea6ea4fb7d916c206062"),
    (20, "13hO6vZmNgWE7chttvCbMaLkN0zYAd44e", 930817, "33d6454f9948d85dfc6932729d8c25bb607e83369fc55979a603f02137e11488"),
]

# Source-side observations already reviewed in #124. They are comparison facts,
# not assertions about the result of this independent exact-chunk scan.
HISTORICAL_FULLBOOK_CANDIDATE_POOL = 3676
HISTORICAL_H10_REVIEW = {
    "observations": 142,
    "structural": 17,
    "nonstructural": 125,
    "ambiguous": 0,
    "ledger_sha256": "fe16d2080fb14b86f6346bcf1efbf1466b3a6a181c8ddb4fc046a4cf5d6612d6",
}

TARGET_SIZES = (15.5, 13.5, 13.0, 10.0)
SIZE_TOLERANCE = 0.18
MARGIN_PT = 44.0
MAX_CLUSTER_CHARS = 260

CAPTION_RE = re.compile(
    r"^(?:table|figure|fig\.?|box|video|plate)\s*[A-Z0-9.-]*\b",
    re.IGNORECASE,
)
SUPPLEMENT_RE = re.compile(
    r"^(?:case study(?: answer)?|summary|references|preparations available|"
    r"study questions|suggested reading|selected reading)\b",
    re.IGNORECASE,
)
CONTINUATION_RE = re.compile(r"^(?:\(?continued\)?|continued\b)", re.IGNORECASE)
LETTERED_RE = re.compile(r"^[A-Z]\.(?:\s|$)")
NUMBERED_RE = re.compile(r"^\d+\.(?:\s|$)")
CHAPTER_RE = re.compile(r"^\s*(\d{1,2})\s+\S")
FOLIO_RE = re.compile(r"^\s*(\d{1,4})\s*$")


@dataclass(frozen=True)
class SourceSpec:
    part_index: int
    drive_id: str
    size_bytes: int
    sha256: str

    @property
    def filename(self) -> str:
        return f"Katzung_{self.part_index}.pdf"


def ws(text: str) -> str:
    return " ".join((text or "").split())


def norm(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "").casefold()
    return "".join(ch for ch in value if ch.isalnum())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dominant_span(line: dict) -> dict | None:
    spans = [span for span in line.get("spans", []) if ws(span.get("text", ""))]
    if not spans:
        return None
    return max(
        spans,
        key=lambda span: (
            len(ws(span.get("text", ""))),
            float(span.get("size", 0.0)),
        ),
    )


def nearest_target_size(size: float) -> float | None:
    candidate = min(TARGET_SIZES, key=lambda target: abs(target - size))
    return candidate if abs(candidate - size) <= SIZE_TOLERANCE else None


def is_heading_style(font: str, flags: int, target_size: float) -> bool:
    # The historical full-book H10 queue was explicitly a 10 pt bold class.
    # Excluding regular/italic body fonts prevents short body lines from being
    # mislabeled as heading-review work.
    if "dingbat" in font.casefold():
        return False
    if target_size == 10.0:
        return bool(flags & 16) or bool(BOLD_FONT_RE.search(font))
    return True


def iter_style_clusters(page) -> Iterable[dict]:
    """Yield adjacent same-style lines in the source body, excluding margins."""
    height = float(page.rect.height)
    for block in page.get_text("dict").get("blocks", []):
        lines = block.get("lines")
        if not lines:
            continue

        current: list[dict] = []
        current_key = None
        last_y1 = None

        def flush():
            nonlocal current, current_key, last_y1
            if not current:
                return None
            text = ws(" ".join(item["text"] for item in current))
            result = {
                "text": text,
                "norm": norm(text),
                "font": current_key[0],
                "size": current_key[1],
                "flags": current_key[2],
                "bbox": [
                    min(item["bbox"][0] for item in current),
                    min(item["bbox"][1] for item in current),
                    max(item["bbox"][2] for item in current),
                    max(item["bbox"][3] for item in current),
                ],
            }
            current = []
            current_key = None
            last_y1 = None
            return result

        for line in lines:
            span = dominant_span(line)
            text = ws("".join(s.get("text", "") for s in line.get("spans", [])))
            bbox = tuple(float(x) for x in line.get("bbox", (0, 0, 0, 0)))
            if (
                span is None
                or not text
                or bbox[1] < MARGIN_PT
                or bbox[3] > height - MARGIN_PT
            ):
                result = flush()
                if result is not None:
                    yield result
                continue

            raw_size = float(span.get("size", 0.0))
            target_size = nearest_target_size(raw_size)
            if target_size is None:
                result = flush()
                if result is not None:
                    yield result
                continue

            font = str(span.get("font", ""))
            flags = int(span.get("flags", 0))
            if not is_heading_style(font, flags, target_size):
                result = flush()
                if result is not None:
                    yield result
                continue

            key = (
                font,
                target_size,
                flags,
            )
            gap = None if last_y1 is None else bbox[1] - last_y1
            if current_key is not None and (
                key != current_key
                or (gap is not None and gap > max(3.0, target_size * 1.3))
            ):
                result = flush()
                if result is not None:
                    yield result

            current_key = key
            current.append({"text": text, "bbox": bbox})
            last_y1 = bbox[3]

        result = flush()
        if result is not None:
            yield result


def classify_candidate(text: str, size: float) -> str:
    """Conservative source-observation classifier.

    Only obvious non-structural classes are excluded. 10 pt observations that
    cannot be deterministically classified remain REVIEW_REQUIRED.
    """
    clean = ws(text)
    if not clean:
        return "empty"
    if len(clean) > MAX_CLUSTER_CHARS:
        return "body_fragment"
    if CAPTION_RE.match(clean):
        return "caption_sidecar"
    if CONTINUATION_RE.match(clean):
        return "continuation_fragment"
    if SUPPLEMENT_RE.match(clean):
        return "supplement_sidecar"
    if size in (15.5, 13.5, 13.0):
        return "structural_candidate"
    if size == 10.0:
        if LETTERED_RE.match(clean) or NUMBERED_RE.match(clean):
            return "structural_candidate_10pt_numbered"
        if clean.endswith(",") or clean.casefold() in {"and", "or"}:
            return "continuation_fragment"
        return "review_required_10pt"
    return "review_required"


def margin_folio_candidates(page) -> list[int]:
    height = float(page.rect.height)
    values: list[int] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            bbox = tuple(float(x) for x in line.get("bbox", (0, 0, 0, 0)))
            if not (bbox[1] <= 72.0 or bbox[3] >= height - 72.0):
                continue
            # Page numbers are often their own span inside a running-header line.
            # Inspect spans individually before falling back to the whole line.
            texts = [
                ws(span.get("text", ""))
                for span in line.get("spans", [])
                if ws(span.get("text", ""))
            ]
            texts.append(ws("".join(span.get("text", "") for span in line.get("spans", []))))
            for text in texts:
                match = FOLIO_RE.match(text)
                if not match:
                    continue
                value = int(match.group(1))
                if 1 <= value <= 1600:
                    values.append(value)
    return sorted(set(values))


def infer_folio_mapping(doc) -> dict:
    """Infer local physical-page -> printed-folio mapping from repeated margins."""
    offset_counts = collections.Counter()
    candidates_by_page: dict[int, list[int]] = {}
    for page_index in range(doc.page_count):
        candidates = margin_folio_candidates(doc[page_index])
        candidates_by_page[page_index] = candidates
        for value in candidates:
            offset_counts[value - page_index] += 1

    if not offset_counts:
        return {
            "resolved": False,
            "reason": "no_margin_folio_candidates",
            "mapping": {},
        }

    offset, support = offset_counts.most_common(1)[0]
    mapping = {
        page_index: page_index + offset
        for page_index, candidates in candidates_by_page.items()
        if page_index + offset in candidates
    }
    coverage = len(mapping) / max(1, doc.page_count)
    resolved = support >= 3 and coverage >= 0.30

    return {
        "resolved": resolved,
        "offset": offset,
        "support_pages": support,
        "coverage_ratio": round(coverage, 4),
        "first_printed_folio": min(mapping.values()) if mapping else None,
        "last_printed_folio": max(mapping.values()) if mapping else None,
        "mapping": mapping,
    }


def chapter_markers(doc) -> list[dict]:
    markers = []
    seen = set()
    for page_index in range(doc.page_count):
        text = doc[page_index].get_text("text")
        for raw_line in text.splitlines():
            line = ws(raw_line)
            match = CHAPTER_RE.match(line)
            if not match or len(line) > 180:
                continue
            chapter = int(match.group(1))
            if not 1 <= chapter <= 67:
                continue
            key = (chapter, page_index, norm(line))
            if key in seen:
                continue
            seen.add(key)
            markers.append(
                {
                    "chapter": chapter,
                    "pdf_page": page_index + 1,
                    "text": line,
                }
            )
    return markers


def reconstruct_candidate_parents(observations: list[dict]) -> None:
    """Add deterministic style-level parent pointers for review, not runtime."""
    stack: list[dict] = []
    level_for_size = {15.5: 1, 13.5: 2, 13.0: 3, 10.0: 4}
    for item in observations:
        if not item["classification"].startswith("structural_candidate"):
            continue
        level = level_for_size[item["size"]]
        while stack and stack[-1]["candidate_level"] >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        item["candidate_level"] = level
        item["candidate_parent_observation_id"] = (
            parent["observation_id"] if parent else None
        )
        stack.append(item)


def audit_part(spec: SourceSpec, path: Path) -> tuple[dict, list[dict]]:
    if path.stat().st_size != spec.size_bytes:
        raise AssertionError(
            f"part {spec.part_index} size mismatch: {path.stat().st_size}"
        )
    digest = sha256_file(path)
    if digest != spec.sha256:
        raise AssertionError(
            f"part {spec.part_index} sha256 mismatch: {digest}"
        )

    doc = fitz.open(path)
    folio = infer_folio_mapping(doc)
    toc = doc.get_toc(simple=True)
    markers = chapter_markers(doc)

    observations: list[dict] = []
    classification_counts = collections.Counter()
    style_counts = collections.Counter()

    for page_index in range(doc.page_count):
        printed = folio["mapping"].get(page_index)
        for cluster_index, cluster in enumerate(iter_style_clusters(doc[page_index])):
            classification = classify_candidate(cluster["text"], cluster["size"])
            classification_counts[classification] += 1
            style_key = f"{cluster['font']}|{cluster['size']}|{cluster['flags']}"
            style_counts[style_key] += 1

            observation_id = (
                f"katzung16e:p{spec.part_index:02d}:"
                f"pdf{page_index + 1:04d}:c{cluster_index:03d}"
            )
            observations.append(
                {
                    "observation_id": observation_id,
                    "part_index": spec.part_index,
                    "drive_id": spec.drive_id,
                    "pdf_page": page_index + 1,
                    "printed_folio": printed,
                    "font": cluster["font"],
                    "size": cluster["size"],
                    "flags": cluster["flags"],
                    "bbox": [round(float(x), 2) for x in cluster["bbox"]],
                    "text": cluster["text"],
                    "text_norm": cluster["norm"],
                    "classification": classification,
                    "page_end": None,
                    "locator_semantics": "heading_point_not_section_range",
                }
            )

    reconstruct_candidate_parents(observations)
    summary = {
        "part_index": spec.part_index,
        "drive_id": spec.drive_id,
        "filename": spec.filename,
        "size_bytes": spec.size_bytes,
        "source_sha256": digest,
        "pdf_pages": doc.page_count,
        "native_outline_entries": len(toc),
        "native_outline_preview": toc[:12],
        "folio": {k: v for k, v in folio.items() if k != "mapping"},
        "chapter_markers": markers,
        "classification_counts": dict(sorted(classification_counts.items())),
        "style_counts": dict(style_counts.most_common()),
    }
    doc.close()
    return summary, observations


def seam_audit(part_summaries: list[dict]) -> list[dict]:
    seams = []
    for left, right in zip(part_summaries, part_summaries[1:]):
        left_folio = left["folio"]
        right_folio = right["folio"]
        left_end = left_folio.get("last_printed_folio")
        right_start = right_folio.get("first_printed_folio")

        if not left_folio.get("resolved") or not right_folio.get("resolved"):
            state = "review_required_folio_unresolved"
        elif right_start == left_end + 1:
            state = "contiguous"
        elif right_start <= left_end:
            state = "overlap_or_repeated_boundary"
        else:
            state = "gap_or_unmapped_boundary"

        seams.append(
            {
                "left_part": left["part_index"],
                "right_part": right["part_index"],
                "left_last_printed_folio": left_end,
                "right_first_printed_folio": right_start,
                "state": state,
            }
        )
    return seams


def main(directory: str) -> None:
    root = Path(directory)
    specs = [SourceSpec(*row) for row in SOURCE_MANIFEST]

    part_summaries = []
    observations = []
    for spec in specs:
        path = root / spec.filename
        if not path.exists():
            raise FileNotFoundError(path)
        summary, rows = audit_part(spec, path)
        part_summaries.append(summary)
        observations.extend(rows)

    seams = seam_audit(part_summaries)
    counts = collections.Counter(row["classification"] for row in observations)
    structural_candidates = sum(
        count
        for label, count in counts.items()
        if label.startswith("structural_candidate")
    )
    review_required = sum(
        count for label, count in counts.items() if label.startswith("review_required")
    )
    seam_review_required = sum(seam["state"] != "contiguous" for seam in seams)

    manifest_payload = [
        {
            "part_index": spec.part_index,
            "drive_id": spec.drive_id,
            "size_bytes": spec.size_bytes,
            "sha256": spec.sha256,
        }
        for spec in specs
    ]
    manifest_sha = hashlib.sha256(
        json.dumps(manifest_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    summary = {
        "logical_source_id": LOGICAL_SOURCE_ID,
        "audit_version": "katzung16e_registered_chunks_v1",
        "pymupdf_version": fitz.VersionBind,
        "registered_chunk_count": len(specs),
        "source_manifest_sha256": manifest_sha,
        "part_summaries": part_summaries,
        "seams": seams,
        "classification_counts": dict(sorted(counts.items())),
        "structural_candidate_observations": structural_candidates,
        "review_required_observations": review_required,
        "seam_review_required_count": seam_review_required,
        "historical_fullbook_candidate_pool": HISTORICAL_FULLBOOK_CANDIDATE_POOL,
        "historical_h10_review": HISTORICAL_H10_REVIEW,
        "candidate_parity_delta_vs_historical_fullbook": (
            structural_candidates - HISTORICAL_FULLBOOK_CANDIDATE_POOL
        ),
        "authoritative_toc_denominator": None,
        "database_write_performed": False,
        "staging_write_performed": False,
        "certificate_write_performed": False,
        "promotion_write_performed": False,
        "page_end_policy": "null",
        "locator_semantics": "heading_point_not_section_range",
        "status": (
            "REVIEW_REQUIRED"
            if review_required or seam_review_required
            else "CANDIDATE_AUDIT_COMPLETE_PENDING_INDEPENDENT_REVIEW"
        ),
        "next_gate": (
            "Review exact finite observation/seam queues, reconcile against printed "
            "Contents/full-book structural inventory, then independently attest an "
            "immutable staging proposal. Candidate parity alone is not a denominator."
        ),
    }

    ledger = {
        "source_manifest": manifest_payload,
        "observations": observations,
        "seams": seams,
    }
    ledger_sha = hashlib.sha256(
        json.dumps(ledger, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    summary["ledger_sha256"] = ledger_sha

    Path("katzung_16e_chunk_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    Path("katzung_16e_chunk_observation_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("Katzung 16e registered-chunk audit")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    # Hard gates: exact source identity only. Review-dependent facts deliberately
    # remain outputs rather than assertions so the audit cannot self-certify.
    if len(part_summaries) != 20:
        raise AssertionError("Expected all 20 registered chunks")
    if any(row["page_end"] is not None for row in observations):
        raise AssertionError("Audit must not infer page_end")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: audit_katzung16e_chunks.py <directory-containing-Katzung_1..20.pdf>"
        )
    main(sys.argv[1])
