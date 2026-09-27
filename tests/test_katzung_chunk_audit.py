from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import fitz


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


def test_chapter_regex_recognizes_numeric_markers_only():
    assert audit.CHAPTER_RE.match("CHAPTER 1")
    assert audit.CHAPTER_RE.match("  Chapter 67  ")
    assert audit.CHAPTER_RE.match("SECTION 1") is None
    assert audit.CHAPTER_RE.match("Chapter One") is None


def test_chapter_markers_keeps_only_required_chapters_1_through_67(tmp_path):
    path = tmp_path / "markers.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "CHAPTER 1\nnot a chapter\nCHAPTER 67\nCHAPTER 68\nSECTION 2",
    )
    doc.save(path)
    doc.close()

    reopened = fitz.open(path)
    markers = audit.chapter_markers(reopened)
    reopened.close()

    assert [item["chapter"] for item in markers] == [1, 67]
