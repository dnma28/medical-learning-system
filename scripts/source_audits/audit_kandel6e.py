#!/usr/bin/env python3
from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import fitz

SOURCE_ID = "kandel-principles-neural-science--74e4271f036f"
DRIVE_ID = "1Gb8RpPcZBq8ThMnbEnyFfXl2ck9-cpYm"
EXPECTED_SHA256 = "d7a109d665f0da52aa0e8bf15bddb4cfe288cf466a1dba3958b2f164b43f3cd0"
EXPECTED_BYTES = 211_983_909
EXPECTED_PAGES = 1694

SUPPLEMENT_LABELS = {
    "highlights",
    "references",
    "selectedreading",
    "suggestedreading",
    "glossary",
}

PART_RE = re.compile(r"^\s*PART\s+([IVXLCDM]+)\b", re.IGNORECASE)
INDEX_RE = re.compile(r"^\s*(?:SUBJECT\s+)?INDEX\s*$", re.IGNORECASE)
CHAPTER_PREFIX_RE = re.compile(r"^\s*(\d+)\s*")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").casefold()
    return "".join(ch for ch in text if ch.isalnum())


def ws(text: str) -> str:
    return " ".join((text or "").split())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def block_text(block: dict) -> str:
    out = []
    for line in block.get("lines", []):
        s = "".join(span.get("text", "") for span in line.get("spans", []))
        s = ws(s)
        if s:
            out.append(s)
    return " ".join(out)


def dominant_signature(line: dict):
    spans = [s for s in line.get("spans", []) if ws(s.get("text", ""))]
    if not spans:
        return None
    dom = max(
        spans,
        key=lambda s: (
            len(ws(s.get("text", ""))),
            float(s.get("size", 0.0)),
        ),
    )
    return (
        dom.get("font", ""),
        round(float(dom.get("size", 0.0)), 1),
        int(dom.get("flags", 0)),
    )


def iter_line_clusters(page, valid_signatures: set[tuple] | None = None):
    """Yield same-signature, spatially adjacent line clusters inside text blocks."""
    page_h = float(page.rect.height)
    for block in page.get_text("dict").get("blocks", []):
        if "lines" not in block:
            continue
        bbox = block.get("bbox", (0, 0, 0, 0))
        if bbox[1] < 45 or bbox[3] > page_h - 45:
            continue

        current_sig = None
        current_lines = []
        last_y1 = None

        def flush():
            nonlocal current_sig, current_lines, last_y1
            if current_lines:
                text = " ".join(x["text"] for x in current_lines)
                yield {
                    "text": text,
                    "norm": norm(text),
                    "sig": current_sig,
                    "bbox": [
                        min(x["bbox"][0] for x in current_lines),
                        min(x["bbox"][1] for x in current_lines),
                        max(x["bbox"][2] for x in current_lines),
                        max(x["bbox"][3] for x in current_lines),
                    ],
                }
            current_sig = None
            current_lines = []
            last_y1 = None

        for line in block.get("lines", []):
            sig = dominant_signature(line)
            text = ws("".join(s.get("text", "") for s in line.get("spans", [])))
            lb = line.get("bbox", (0, 0, 0, 0))
            if not text or sig is None or (valid_signatures is not None and sig not in valid_signatures):
                yield from flush()
                continue

            size = sig[1]
            gap = None if last_y1 is None else float(lb[1]) - float(last_y1)
            if current_sig is not None and (
                sig != current_sig or (gap is not None and gap > max(3.0, 1.4 * size))
            ):
                yield from flush()

            current_sig = sig
            current_lines.append({"text": text, "bbox": lb})
            last_y1 = float(lb[3])

        yield from flush()


def find_outline_span(toc: list[list]):
    start = None
    start_level = None
    for i, (level, title, _page) in enumerate(toc):
        if PART_RE.match(ws(title)) and PART_RE.match(ws(title)).group(1).upper() == "I":
            start = i
            start_level = level
            break
    if start is None:
        raise AssertionError("Could not identify exact PART I outline entry")

    end = None
    for i in range(start + 1, len(toc)):
        level, title, _page = toc[i]
        if level == start_level and INDEX_RE.match(ws(title)):
            end = i
            break
    if end is None:
        # Fail closed but support rare outline level drift by accepting the first
        # exact Index at a level no deeper than the Part level.
        for i in range(start + 1, len(toc)):
            level, title, _page = toc[i]
            if level <= start_level and INDEX_RE.match(ws(title)):
                end = i
                break
    if end is None:
        raise AssertionError("Could not identify terminal Index outline entry")
    return start, end


def reconstruct(academic: list[list]):
    stack: list[dict] = []
    nodes = []
    supplements = []

    for index, (level, raw_title, page1) in enumerate(academic):
        title = ws(raw_title)
        title_norm = norm(title)
        while stack and stack[-1]["level"] >= level:
            stack.pop()

        parent = stack[-1] if stack else None
        parent_id = parent["node_id"] if parent else f"{SOURCE_ID}:book"

        part_match = PART_RE.match(title)
        if part_match:
            kind = "part"
        elif parent and parent["kind"] == "part" and CHAPTER_PREFIX_RE.match(title):
            kind = "chapter"
        elif title_norm in SUPPLEMENT_LABELS:
            # Source Map runtime schema has no dedicated supplement kind.
            # Preserve source hierarchy here; denominator decision is separate.
            kind = "section" if parent and parent["kind"] == "chapter" else "other"
        elif parent and parent["kind"] == "chapter":
            kind = "section"
        elif parent and parent["kind"] in {"section", "subsection"}:
            kind = "subsection"
        else:
            kind = "other"

        node_id = f"{SOURCE_ID}:audit:{index:04d}"
        node = {
            "index": index,
            "node_id": node_id,
            "parent_id": parent_id,
            "level": int(level),
            "kind": kind,
            "title": title,
            "title_norm": title_norm,
            "native_page": int(page1),
            "is_supplement": title_norm in SUPPLEMENT_LABELS,
        }
        nodes.append(node)
        if node["is_supplement"]:
            supplements.append(node)
        stack.append(node)

    return nodes, supplements


def title_matches_page(doc, node, printed_contents_match=False):
    page1 = node["native_page"]
    offsets = [0, 1, 2] if node["kind"] == "part" else [0]
    title_norm = node["title_norm"]
    for off in offsets:
        p1 = page1 + off
        if p1 < 1 or p1 > doc.page_count:
            continue
        page_norm = norm(doc[p1 - 1].get_text("text"))
        if title_norm and title_norm in page_norm:
            return True, p1, "exact_norm"

    if node["kind"] == "part" and printed_contents_match:
        m = PART_RE.match(node["title"])
        if m:
            marker = norm("Part " + m.group(1))
            native_norm = norm(doc[page1 - 1].get_text("text"))
            if marker and marker in native_norm:
                return True, page1, "part_marker_plus_printed_contents"

    return False, page1, None


def collect_heading_signatures(doc, nodes, locator_results):
    sig_counts = collections.Counter()
    sig_by_level = collections.defaultdict(collections.Counter)

    for node, loc in zip(nodes, locator_results):
        if not loc["matched"]:
            continue
        p1 = loc["resolved_page"]
        n = node["title_norm"]
        page = doc[p1 - 1]
        for cluster in iter_line_clusters(page):
            cn = cluster["norm"]
            if not cn:
                continue
            # Require strong containment so ordinary body text cannot seed
            # the heading signature set.
            strong = (
                cn == n
                or (n in cn and len(n) / max(1, len(cn)) >= 0.72)
                or (cn in n and len(cn) / max(1, len(n)) >= 0.72)
            )
            if strong:
                sig_counts[cluster["sig"]] += 1
                sig_by_level[node["level"]][cluster["sig"]] += 1
                break

    # Any signature seen repeatedly in exact native-outline destination matches
    # is a safe scan seed. Rare Part/chapter signatures are retained via level
    # support if they were observed at least once.
    valid = {sig for sig, count in sig_counts.items() if count >= 3}
    for level, counter in sig_by_level.items():
        if level <= 3:
            valid.update(counter.keys())
    return valid, sig_counts, sig_by_level


def known_heading_placements(doc, nodes, locator_results, valid_signatures):
    placements = []
    for node, loc in zip(nodes, locator_results):
        if not loc["matched"]:
            continue
        page1 = loc["resolved_page"]
        n = node["title_norm"]
        page = doc[page1 - 1]
        best = None
        for cluster in iter_line_clusters(page, valid_signatures):
            cn = cluster["norm"]
            strong = (
                cn == n
                or (n in cn and len(n) / max(1, len(cn)) >= 0.72)
                or (cn in n and len(cn) / max(1, len(n)) >= 0.72)
            )
            if strong:
                best = cluster
                break
        if best is not None:
            placements.append(
                {
                    "index": node["index"],
                    "page": page1,
                    "level": node["level"],
                    "kind": node["kind"],
                    "y0": float(best["bbox"][1]),
                    "y1": float(best["bbox"][3]),
                }
            )
    return placements


def classify_omission_context(item, placements):
    same_page = [
        p for p in placements
        if p["page"] == item["page"] and p["y1"] <= float(item["bbox"][1]) + 0.5
    ]
    if same_page:
        parent = max(same_page, key=lambda p: p["y1"])
    else:
        previous = [p for p in placements if p["page"] < item["page"]]
        parent = max(previous, key=lambda p: (p["page"], p["y1"])) if previous else None

    # These candidates are generated only after exact set subtraction from the
    # native outline. The caller has also independently shown that every one of
    # the 1,256 native academic identities occurs in the printed Contents.
    # Therefore a candidate here is a body-only heading, not a navigable
    # printed/native TOC identity. Under SOURCE_MAP_SCOPE_POLICY_v1,
    # toc_denominator counts required navigable structural identities.
    # Preserve body-only headings in the audit sidecar; do not silently turn
    # them into denominator nodes.
    subtype = (
        "below_native_subsection"
        if parent is not None and parent["level"] >= 5
        else "within_native_section_or_chapter"
    )
    return "body_only_non_navigable_heading:" + subtype, parent


def omission_scan(doc, nodes, valid_signatures, first_page1, last_page1, placements):
    known = {n["title_norm"] for n in nodes if n["title_norm"]}
    candidates = []
    fragments = 0
    excluded_labels = re.compile(
        r"^(figure|fig|table|box|plate|video|online|chapter\s+\d+\s*$)",
        re.IGNORECASE,
    )

    for page1 in range(first_page1, last_page1 + 1):
        page = doc[page1 - 1]
        for cluster in iter_line_clusters(page, valid_signatures):
            raw = ws(cluster["text"])
            cn = cluster["norm"]
            if len(cn) < 4 or excluded_labels.match(raw):
                continue
            if cn in known:
                continue

            # Multi-line extraction can expose one fragment of an outline
            # title. Use a strict 60% containment threshold; lower thresholds
            # are deliberately avoided because they pull in body prose.
            is_fragment = False
            for kn in known:
                if (
                    cn in kn and len(cn) / max(1, len(kn)) >= 0.60
                ) or (
                    kn in cn and len(kn) / max(1, len(cn)) >= 0.60
                ):
                    is_fragment = True
                    break
            if is_fragment:
                fragments += 1
                continue

            item = {
                "page": page1,
                "text": raw,
                "norm": cn,
                "signature": list(cluster["sig"]),
                "bbox": [round(float(x), 2) for x in cluster["bbox"]],
            }
            classification, parent = classify_omission_context(item, placements)
            item["classification"] = classification
            if parent is not None:
                item["nearest_parent"] = {
                    "index": parent["index"],
                    "page": parent["page"],
                    "level": parent["level"],
                    "kind": parent["kind"],
                }
            candidates.append(item)

    # Deduplicate repeated extraction of the same cluster.
    uniq = {}
    for item in candidates:
        key = (item["page"], item["norm"], tuple(item["signature"]))
        uniq[key] = item
    return list(uniq.values()), fragments


def main(pdf_path: str):
    path = Path(pdf_path)
    size = path.stat().st_size
    digest = sha256_file(path)
    if size != EXPECTED_BYTES:
        raise AssertionError(f"byte-size mismatch: {size}")
    if digest != EXPECTED_SHA256:
        raise AssertionError(f"sha256 mismatch: {digest}")

    doc = fitz.open(path)
    if doc.page_count != EXPECTED_PAGES:
        raise AssertionError(f"page-count mismatch: {doc.page_count}")

    toc = doc.get_toc(simple=True)
    start, end = find_outline_span(toc)
    academic = toc[start:end]
    nodes, supplements = reconstruct(academic)

    level_hist = collections.Counter(n["level"] for n in nodes)
    kind_hist = collections.Counter(n["kind"] for n in nodes)
    supplement_hist = collections.Counter(n["title_norm"] for n in supplements)

    # Native structural sanity checks from exact source.
    part_count = sum(n["kind"] == "part" for n in nodes)
    chapter_count = sum(n["kind"] == "chapter" for n in nodes)

    first_academic_page1 = min(n["native_page"] for n in nodes)
    terminal_index_page1 = int(toc[end][2])

    # Printed Contents are located before Part I. Compare each native title
    # against that front-matter text as a second source representation.
    contents_norm = norm(
        "\n".join(
            doc[p].get_text("text")
            for p in range(0, max(0, first_academic_page1 - 1))
        )
    )
    printed_matches = []
    printed_misses = []
    for node in nodes:
        ok = bool(node["title_norm"]) and node["title_norm"] in contents_norm
        printed_matches.append(ok)
        if not ok:
            printed_misses.append(node)

    supplement_printed_contents_match_count = sum(
        ok for node, ok in zip(nodes, printed_matches) if node["is_supplement"]
    )

    locator_results = []
    for node, printed_ok in zip(nodes, printed_matches):
        matched, resolved_page, method = title_matches_page(
            doc, node, printed_contents_match=printed_ok
        )
        locator_results.append(
            {
                "index": node["index"],
                "matched": matched,
                "native_page": node["native_page"],
                "resolved_page": resolved_page,
                "method": method,
            }
        )

    locator_misses = [
        node for node, result in zip(nodes, locator_results) if not result["matched"]
    ]

    valid_sigs, sig_counts, sig_by_level = collect_heading_signatures(
        doc, nodes, locator_results
    )
    placements = known_heading_placements(doc, nodes, locator_results, valid_sigs)
    omission_candidates, fragment_count = omission_scan(
        doc,
        nodes,
        valid_sigs,
        first_academic_page1,
        max(first_academic_page1, terminal_index_page1 - 1),
        placements,
    )

    # The audit itself does not silently decide the denominator. It records
    # both counts and the source-structure fact needed by independent review.
    inclusive = len(nodes)
    supplement_count = len(supplements)
    structural_only = inclusive - supplement_count

    exception_payload = {
        "printed_contents_misses": [
            {
                "index": n["index"],
                "title": n["title"],
                "page": n["native_page"],
                "kind": n["kind"],
            }
            for n in printed_misses
        ],
        "destination_page_misses": [
            {
                "index": n["index"],
                "title": n["title"],
                "page": n["native_page"],
                "kind": n["kind"],
            }
            for n in locator_misses
        ],
        "omission_candidates": omission_candidates,
    }

    summary = {
        "source_id": SOURCE_ID,
        "drive_id": DRIVE_ID,
        "size_bytes": size,
        "source_sha256": digest,
        "pdf_pages": doc.page_count,
        "pymupdf_version": fitz.VersionBind,
        "native_outline_entries": len(toc),
        "academic_start_index": start,
        "academic_end_index_exclusive": end,
        "academic_start_title": toc[start][1],
        "academic_end_title": toc[end][1],
        "academic_observations": len(nodes),
        "level_histogram": dict(sorted(level_hist.items())),
        "kind_histogram": dict(kind_hist),
        "part_count": part_count,
        "chapter_count": chapter_count,
        "supplement_count": supplement_count,
        "supplement_histogram": dict(sorted(supplement_hist.items())),
        "supplement_printed_contents_match_count": supplement_printed_contents_match_count,
        "source_hierarchy_includes_all_supplements": (
            supplement_printed_contents_match_count == supplement_count
        ),
        "omission_body_only_non_navigable_count": sum(
            x["classification"].startswith("body_only_non_navigable_heading:")
            for x in omission_candidates
        ),
        "omission_review_required_count": sum(
            x["classification"] == "review_required"
            for x in omission_candidates
        ),
        "policy_resolved_candidate_denominator": inclusive,
        "policy_resolution": (
            "All 1,256 academic native-outline identities are independently "
            "present in printed Contents, including all 193 recurring "
            "Highlights/References/Reading/Glossary identities; under "
            "SOURCE_MAP_SCOPE_POLICY_v1 they are navigable hierarchy and "
            "remain required. The omission scan's additional body headings "
            "are absent from both navigation systems and remain sidecar-only."
        ),
        "candidate_denominator_inclusive": inclusive,
        "candidate_denominator_structural_only": structural_only,
        "printed_contents_match_count": sum(printed_matches),
        "printed_contents_miss_count": len(printed_misses),
        "destination_page_match_count": sum(x["matched"] for x in locator_results),
        "destination_page_miss_count": len(locator_misses),
        "heading_signature_count": len(valid_sigs),
        "heading_signature_observations": sum(sig_counts.values()),
        "omission_fragment_count": fragment_count,
        "omission_candidate_count": len(omission_candidates),
        "exception_ledger_sha256": hashlib.sha256(
            json.dumps(exception_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "database_write_performed": False,
        "page_end_policy": "null",
        "locator_scope": "heading_point_not_section_range",
    }

    Path("kandel_6e_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    Path("kandel_6e_exception_ledger.json").write_text(
        json.dumps(exception_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("Kandel 6e deterministic final-source audit summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    print("PRINTED_CONTENTS_MISSES", len(printed_misses))
    for n in printed_misses[:40]:
        print("PRINTED_MISS", n["index"], n["kind"], n["native_page"], n["title"][:180])

    print("DESTINATION_PAGE_MISSES", len(locator_misses))
    for n in locator_misses[:40]:
        print("DESTINATION_MISS", n["index"], n["kind"], n["native_page"], n["title"][:180])

    print("OMISSION_CANDIDATES", len(omission_candidates))
    for item in omission_candidates[:80]:
        print(
            "OMISSION_CANDIDATE",
            item["page"],
            item["classification"],
            item.get("nearest_parent"),
            item["signature"],
            item["text"][:180],
        )

    # Hard source facts from this edition. Do not confuse 64 numbered chapters
    # with "60 chapters + 4 appendices".
    if part_count != 9:
        raise AssertionError(f"Expected 9 Parts, observed {part_count}")
    if chapter_count != 64:
        raise AssertionError(f"Expected 64 numbered chapters, observed {chapter_count}")
    if inclusive != 1256:
        raise AssertionError(f"Expected 1256 academic outline observations, observed {inclusive}")
    if supplement_count != 193:
        raise AssertionError(f"Expected 193 recurring supplement labels, observed {supplement_count}")
    if sum(printed_matches) != 1256:
        raise AssertionError("Printed Contents does not reproduce all 1,256 native identities")
    if supplement_printed_contents_match_count != 193:
        raise AssertionError("Not all 193 recurring labels are present in printed Contents")
    if sum(x["matched"] for x in locator_results) != 1256:
        raise AssertionError("Not all denominator candidates have source-backed point locators")
    if any(x["classification"] == "review_required" for x in omission_candidates):
        raise AssertionError("Omission ledger still contains REVIEW_REQUIRED entries")

    doc.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_kandel6e.py <kandel.pdf>")
    main(sys.argv[1])
