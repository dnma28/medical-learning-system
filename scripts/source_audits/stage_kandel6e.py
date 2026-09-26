#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import fitz

from scripts.source_audits.audit_kandel6e import (
    DRIVE_ID,
    EXPECTED_BYTES,
    EXPECTED_PAGES,
    EXPECTED_SHA256,
    SOURCE_ID,
    find_outline_span,
    norm,
    reconstruct,
    sha256_file,
    title_matches_page,
)

LOGICAL_SOURCE_ID = "kandel-principles-neural-science"
STAGING_VERSION = 1
TOC_DENOMINATOR = 1256
EXPECTED_NODE_COUNT = 1257
AUDIT_MAIN_COMMIT = "8658c5e2f65d9a5f7b2c656b5f1372cdae7c45f1"
AUDIT_RUN_ID = "36235898309"
AUDIT_ARTIFACT_DIGEST = "358c51c21bbdca32222d507a4e9b19b584273fbef727feac0332d32ff847a051"
EXPECTED_EXCEPTION_LEDGER_SHA = "eed19d02d0becf10e44304b97e46b1cd0c85aab4ff75ded43a930bca55ca6a46"
EXTRACTION_VERSION = (
    "PyMuPDF 1.26.6; get_toc(simple=True)+page.get_text('text'); "
    "page text UTF-8 joined by U+000C; NFKD alphanumeric casefold"
)
REVIEWER_ID = "owner-supplied-external-kandel-final-audit-2026-09-26"
BACKEND_VERIFIER_ID = "gpt-5.6-sol-kandel-backend-verifier-2026-09-26"
QA_RUN_ID = "kandel-v1-final-source-stage-2026-09-26"


def canonical_sha(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def extraction_sha256(doc: fitz.Document) -> str:
    h = hashlib.sha256()
    for page_index in range(doc.page_count):
        if page_index:
            h.update(b"\x0c")
        h.update(doc[page_index].get_text("text").encode("utf-8"))
    return h.hexdigest()


def build_stage(pdf_path: Path):
    if pdf_path.stat().st_size != EXPECTED_BYTES:
        raise AssertionError("Kandel byte-size mismatch")
    if sha256_file(pdf_path) != EXPECTED_SHA256:
        raise AssertionError("Kandel source SHA-256 mismatch")

    summary = json.loads(Path("kandel_6e_audit_summary.json").read_text(encoding="utf-8"))
    exceptions = json.loads(Path("kandel_6e_exception_ledger.json").read_text(encoding="utf-8"))

    assert summary["source_id"] == SOURCE_ID
    assert summary["drive_id"] == DRIVE_ID
    assert summary["source_sha256"] == EXPECTED_SHA256
    assert summary["size_bytes"] == EXPECTED_BYTES
    assert summary["pdf_pages"] == EXPECTED_PAGES
    assert summary["academic_observations"] == TOC_DENOMINATOR
    assert summary["policy_resolved_candidate_denominator"] == TOC_DENOMINATOR
    assert summary["printed_contents_match_count"] == TOC_DENOMINATOR
    assert summary["printed_contents_miss_count"] == 0
    assert summary["destination_page_match_count"] == TOC_DENOMINATOR
    assert summary["destination_page_miss_count"] == 0
    assert summary["supplement_count"] == 193
    assert summary["supplement_printed_contents_match_count"] == 193
    assert summary["source_hierarchy_includes_all_supplements"] is True
    assert summary["omission_candidate_count"] == 25
    assert summary["omission_body_only_non_navigable_count"] == 25
    assert summary["omission_review_required_count"] == 0
    assert summary["database_write_performed"] is False
    assert summary["locator_scope"] == "heading_point_not_section_range"
    assert summary["page_end_policy"] == "null"
    assert summary["exception_ledger_sha256"] == EXPECTED_EXCEPTION_LEDGER_SHA

    doc = fitz.open(pdf_path)
    if doc.page_count != EXPECTED_PAGES:
        raise AssertionError("Kandel page-count mismatch")

    toc = doc.get_toc(simple=True)
    start, end = find_outline_span(toc)
    academic = toc[start:end]
    nodes, supplements = reconstruct(academic)

    assert len(nodes) == TOC_DENOMINATOR
    assert len(supplements) == 193
    assert sum(n["kind"] == "part" for n in nodes) == 9
    assert sum(n["kind"] == "chapter" for n in nodes) == 64
    assert sum(n["kind"] == "section" for n in nodes) == 552
    assert sum(n["kind"] == "subsection" for n in nodes) == 631
    assert all(n["kind"] in {"part", "chapter", "section", "subsection"} for n in nodes)

    first_academic_page1 = min(n["native_page"] for n in nodes)
    contents_norm = norm("\n".join(doc[p].get_text("text") for p in range(first_academic_page1 - 1)))

    printed = []
    locators = []
    for node in nodes:
        printed_ok = bool(node["title_norm"]) and node["title_norm"] in contents_norm
        printed.append(printed_ok)
        matched, resolved_page, method = title_matches_page(
            doc, node, printed_contents_match=printed_ok
        )
        locators.append(
            {
                "matched": matched,
                "resolved_page": int(resolved_page),
                "method": method,
            }
        )

    assert all(printed)
    assert all(x["matched"] for x in locators)

    extraction_sha = extraction_sha256(doc)
    doc.close()

    review_packet = {
        "audit_main_commit": AUDIT_MAIN_COMMIT,
        "audit_run_id": AUDIT_RUN_ID,
        "audit_artifact_digest": AUDIT_ARTIFACT_DIGEST,
        "summary": summary,
        "exceptions": exceptions,
        "owner_supplied_review_basis": {
            "type": "external_audit_report_supplied_by_project_owner",
            "date": "2026-09-26",
            "resolution": (
                "The external audit identified the Roman-prefix, Part-page window, "
                "numeric-title hierarchy, multiline-heading, and Index-boundary defects "
                "and required a full printed-Contents/body-heading reconciliation before "
                "choosing a denominator. The corrected deterministic main run satisfies "
                "those conditions: printed Contents 1256/1256, point locators 1256/1256, "
                "193/193 recurring identities in source navigation, and zero unresolved "
                "omission candidates."
            ),
        },
    }
    toc_reconciliation_sha = canonical_sha(review_packet)

    book_id = f"{LOGICAL_SOURCE_ID}:book"
    proposal = [
        {
            "node_id": book_id,
            "parent_id": None,
            "source_id": None,
            "kind": "book",
            "title": "Principles of Neural Science, Sixth Edition",
            "depth": 0,
            "order_index": 0,
            "page_start": None,
            "page_end": None,
            "source_anchor": {},
            "learning_value": None,
            "freshness_required": False,
            "required": True,
            "status": "verified",
            "issues": [],
        }
    ]

    depth_by_id = {book_id: 0}
    for offset, (node, printed_ok, locator) in enumerate(zip(nodes, printed, locators), start=1):
        parent_id = node["parent_id"]
        if parent_id == f"{SOURCE_ID}:book":
            parent_id = book_id
        if parent_id not in depth_by_id:
            raise AssertionError(f"Parent not yet available: {parent_id}")
        depth = depth_by_id[parent_id] + 1
        depth_by_id[node["node_id"]] = depth

        proposal.append(
            {
                "node_id": node["node_id"],
                "parent_id": parent_id,
                "source_id": SOURCE_ID,
                "kind": node["kind"],
                "title": node["title"],
                "depth": depth,
                "order_index": offset,
                "page_start": locator["resolved_page"],
                "page_end": None,
                "source_anchor": {
                    "scope": "heading_point_not_section_range",
                    "drive_id": DRIVE_ID,
                    "native_outline_index": node["index"],
                    "native_outline_level": node["level"],
                    "native_outline_page": node["native_page"],
                    "resolved_pdf_page": locator["resolved_page"],
                    "locator_match_method": locator["method"],
                    "printed_contents_present": printed_ok,
                    "audit_main_commit": AUDIT_MAIN_COMMIT,
                    "audit_run_id": AUDIT_RUN_ID,
                },
                "source_sha256": EXPECTED_SHA256,
                "extraction_sha256": extraction_sha,
                "extraction_version": EXTRACTION_VERSION,
                "learning_value": None,
                "freshness_required": False,
                "required": True,
                "status": "verified",
                "issues": [],
            }
        )

    assert len(proposal) == EXPECTED_NODE_COUNT
    assert len({n["node_id"] for n in proposal}) == EXPECTED_NODE_COUNT
    assert len({n["order_index"] for n in proposal}) == EXPECTED_NODE_COUNT
    assert all(n["page_end"] is None for n in proposal)

    source_manifest = {
        SOURCE_ID: {
            "drive_id": DRIVE_ID,
            "source_sha256": EXPECTED_SHA256,
            "size_bytes": EXPECTED_BYTES,
            "pdf_pages": EXPECTED_PAGES,
            "extraction_sha256": extraction_sha,
            "extraction_version": EXTRACTION_VERSION,
        }
    }

    audit_metadata = {
        "scope": "full_book",
        "status": "independent_review_conditions_satisfied",
        "reviewer_id": REVIEWER_ID,
        "reviewer_identity_status": (
            "external audit artifact supplied by project owner; personal identity not independently verified"
        ),
        "backend_verifier_id": BACKEND_VERIFIER_ID,
        "qa_run_id": QA_RUN_ID,
        "toc_reconciliation_sha256": toc_reconciliation_sha,
        "toc_evidence": {
            "source_id": SOURCE_ID,
            "locator": f"gdrive:{DRIVE_ID}",
            "source_sha256": EXPECTED_SHA256,
        },
        "required_review_required": "0",
        "required_source_gap": "0",
        "unclassified_observations": "0",
        "qa": {
            "toc_coverage_valid": True,
            "hierarchy_valid": True,
            "locator_qa_passed": True,
            "fingerprint_valid": True,
            "extraction_valid": True,
            "staging_qa_passed": True,
        },
        "counts": {
            "parts": 9,
            "chapters": 64,
            "sections": 552,
            "subsections": 631,
            "required_structural_identities": TOC_DENOMINATOR,
            "proposal_nodes_including_book": EXPECTED_NODE_COUNT,
            "recurring_source_navigation_identities": 193,
            "body_only_non_navigable_sidecar": 25,
        },
        "source_scope_resolution": {
            "candidate_denominator_inclusive": 1256,
            "candidate_denominator_structural_only": 1063,
            "resolved_denominator": 1256,
            "reason": (
                "All 193 recurring Highlights/References/Selected Reading/Suggested Reading/Glossary "
                "identities are present in both native PDF navigation and printed Contents. "
                "Under SOURCE_MAP_SCOPE_POLICY_v1, source-defined navigable hierarchy is required. "
                "The 25 additional typography headings are absent from both navigation systems and "
                "remain body-only sidecar evidence."
            ),
        },
        "source_map_scope_policy": "docs/source_map_scope_policy.md",
        "audit_main_commit": AUDIT_MAIN_COMMIT,
        "audit_run_id": AUDIT_RUN_ID,
        "audit_artifact_digest": AUDIT_ARTIFACT_DIGEST,
        "exception_ledger_sha256": EXPECTED_EXCEPTION_LEDGER_SHA,
        "locator_semantics": "heading_point_not_section_range",
        "page_end_policy": "null",
        "learning_value_policy": "null; curriculum remains separate",
        "database_write_scope": "immutable staging only",
    }

    return {
        "logical_source_id": LOGICAL_SOURCE_ID,
        "staging_version": STAGING_VERSION,
        "proposal": proposal,
        "toc_denominator": TOC_DENOMINATOR,
        "extraction_version": EXTRACTION_VERSION,
        "source_manifest": source_manifest,
        "audit_metadata": audit_metadata,
        "extraction_sha256": extraction_sha,
        "toc_reconciliation_sha256": toc_reconciliation_sha,
    }


def request(method: str, path: str, payload=None):
    base = os.environ["MLS_SUPABASE_URL"].rstrip("/")
    key = os.environ["MLS_SUPABASE_SECRET_KEY"]
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read().decode("utf-8")
            return None if not raw else json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"Supabase {method} {path} HTTP {exc.code}: {body}") from None


def get_rows(table: str, **params):
    return request("GET", f"/rest/v1/{table}?{urllib.parse.urlencode(params)}")


def rpc(name: str, **payload):
    return request("POST", f"/rest/v1/rpc/{name}", payload)


def main():
    pdf = Path("kandel.pdf")
    stage = build_stage(pdf)

    source_rows = get_rows(
        "mls_sources",
        select="source_id,logical_source_id,content_sha256,size_bytes",
        source_id=f"eq.{SOURCE_ID}",
    )
    assert len(source_rows) == 1, source_rows
    source = source_rows[0]
    assert source["logical_source_id"] == LOGICAL_SOURCE_ID, source
    assert source["content_sha256"] == EXPECTED_SHA256, source
    assert source["size_bytes"] == EXPECTED_BYTES, source

    logical_rows = get_rows(
        "mls_logical_sources",
        select="logical_source_id,source_map_version,promoted_staging_version,promoted_certificate_sha256",
        logical_source_id=f"eq.{LOGICAL_SOURCE_ID}",
    )
    assert len(logical_rows) == 1, logical_rows
    logical = logical_rows[0]
    assert logical["source_map_version"] == 0, logical
    assert logical["promoted_staging_version"] is None, logical
    assert logical["promoted_certificate_sha256"] is None, logical

    cert_rows = get_rows(
        "mls_source_map_certificates",
        select="staging_version,certificate_sha256",
        logical_source_id=f"eq.{LOGICAL_SOURCE_ID}",
    )
    assert cert_rows == [], cert_rows

    runtime_rows = get_rows(
        "mls_source_map_nodes",
        select="node_id",
        logical_source_id=f"eq.{LOGICAL_SOURCE_ID}",
    )
    assert runtime_rows == [], len(runtime_rows)

    existing = get_rows(
        "mls_source_map_staging",
        select="staging_version,payload_sha256,toc_denominator,audit_metadata",
        logical_source_id=f"eq.{LOGICAL_SOURCE_ID}",
        order="staging_version.desc",
        limit="1",
    )

    inserted = False
    if existing:
        row = existing[0]
        assert row["staging_version"] == STAGING_VERSION, row
        assert row["toc_denominator"] == TOC_DENOMINATOR, row
        assert row["audit_metadata"].get("qa_run_id") == QA_RUN_ID, row["audit_metadata"]
        payload_sha = row["payload_sha256"]
    else:
        payload = {
            "logical_source_id": stage["logical_source_id"],
            "staging_version": stage["staging_version"],
            "proposal": stage["proposal"],
            "toc_denominator": stage["toc_denominator"],
            "extraction_version": stage["extraction_version"],
            "source_manifest": stage["source_manifest"],
            "audit_metadata": stage["audit_metadata"],
        }
        rows = request("POST", "/rest/v1/mls_source_map_staging", payload)
        assert isinstance(rows, list) and len(rows) == 1, rows
        row = rows[0]
        payload_sha = row["payload_sha256"]
        inserted = True

    validator_sha = rpc(
        "mls_validate_source_map_stage",
        p_logical_source_id=LOGICAL_SOURCE_ID,
        p_staging_version=STAGING_VERSION,
    )
    assert validator_sha == payload_sha, (validator_sha, payload_sha)

    result = {
        "logical_source_id": LOGICAL_SOURCE_ID,
        "source_id": SOURCE_ID,
        "staging_version": STAGING_VERSION,
        "toc_denominator": TOC_DENOMINATOR,
        "proposal_nodes": EXPECTED_NODE_COUNT,
        "payload_sha256": payload_sha,
        "validator_sha256": validator_sha,
        "source_sha256": EXPECTED_SHA256,
        "extraction_sha256": stage["extraction_sha256"],
        "toc_reconciliation_sha256": stage["toc_reconciliation_sha256"],
        "reviewer_id": REVIEWER_ID,
        "backend_verifier_id": BACKEND_VERIFIER_ID,
        "inserted": inserted,
        "certificate_count": 0,
        "runtime_nodes": 0,
        "runtime_version": 0,
        "status": "CERTIFICATE_READY",
    }
    Path("kandel_6e_staging_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print("KANDEL_STAGE_PASS")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
