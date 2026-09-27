from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "source_audits"
    / "audit_katzung16e_chunks.py"
)
SPEC = importlib.util.spec_from_file_location("audit_katzung16e_chunks", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class FakePage:
    def __init__(self, text: str):
        self.text = text

    def get_text(self, mode: str):
        assert mode == "text"
        return self.text


class FakeDoc:
    def __init__(self, pages: list[str]):
        self.pages = [FakePage(page) for page in pages]
        self.page_count = len(self.pages)

    def __getitem__(self, index: int):
        return self.pages[index]


def test_chapter_regex_accepts_source_header_not_prose_reference():
    assert audit.CHAPTER_RE.match("CHAPTER 1 Introduction")
    assert audit.CHAPTER_RE.match("  CHAPTER 67 Important Drug Interactions")
    assert audit.CHAPTER_RE.match("Chapter 24)") is None
    assert audit.CHAPTER_RE.match("CHAPTER 59)") is None
    assert audit.CHAPTER_RE.match("SECTION 1 Receptors") is None


def test_chapter_markers_deduplicate_running_headers_and_keep_1_through_67():
    doc = FakeDoc(
        [
            "CHAPTER 1 Introduction 3\nbody\nCHAPTER 1 Introduction 5",
            "Chapter 24) is a prose reference\nCHAPTER 59)",
            "CHAPTER 67 Important Drug Interactions 1253\nCHAPTER 68 Out of scope",
        ]
    )

    markers = audit.chapter_markers(doc)

    assert [item["chapter"] for item in markers] == [1, 67]
    assert [item["pdf_page"] for item in markers] == [1, 3]

def test_classifier_keeps_ambiguous_bold_10pt_for_review():
    assert audit.classify_candidate("Clinical use in special populations", 10.0) == (
        "review_required_10pt"
    )


def test_classifier_separates_obvious_caption_and_numbered_heading():
    assert audit.classify_candidate("TABLE 1.2 Drug Effects", 10.0) == "caption_sidecar"
    assert audit.classify_candidate("A. Pharmacokinetics", 10.0) == (
        "structural_candidate_10pt_numbered"
    )
    assert audit.classify_candidate("(Continued)", 10.0) == "continuation_fragment"


def test_seam_audit_never_silently_repairs_printed_folio_gap():
    parts = [
        {
            "part_index": 2,
            "folio": {
                "resolved": True,
                "first_printed_folio": 57,
                "last_printed_folio": 90,
            },
        },
        {
            "part_index": 3,
            "folio": {
                "resolved": True,
                "first_printed_folio": 93,
                "last_printed_folio": 140,
            },
        },
    ]

    seams = audit.seam_audit(parts)

    assert seams == [
        {
            "left_part": 2,
            "right_part": 3,
            "left_last_printed_folio": 90,
            "right_first_printed_folio": 93,
            "state": "gap_or_unmapped_boundary",
        }
    ]


def test_source_manifest_stays_exact_and_complete():
    assert len(audit.SOURCE_MANIFEST) == 20
    assert [row[0] for row in audit.SOURCE_MANIFEST] == list(range(1, 21))
    assert len({row[1] for row in audit.SOURCE_MANIFEST}) == 20
    assert all(len(row[3]) == 64 for row in audit.SOURCE_MANIFEST)


def test_missing_pdf_tooling_fails_clearly(monkeypatch):
    monkeypatch.setattr(audit, "fitz", None)
    with pytest.raises(RuntimeError, match="PyMuPDF"):
        audit.require_fitz()
