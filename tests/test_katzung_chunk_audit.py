from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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
    assert audit.CHAPTER_RE.match("CHAPTER 68 Out of scope")


def test_chapter_markers_deduplicates_running_headers_and_keeps_1_through_67():
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
