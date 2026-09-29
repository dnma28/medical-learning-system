from pathlib import Path
import sys

import pytest

fitz = pytest.importorskip("fitz")

from medical_learning_system.pdf_preflight import inspect_pdf, main


def _pdf(path: Path) -> None:
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), "Source heading with readable native text")
        doc.new_page()
        doc.save(path)


def test_preflight_records_exact_physical_pages_and_visual_queue(tmp_path: Path):
    path = tmp_path / "mixed.pdf"
    _pdf(path)
    whole = inspect_pdf(path)
    assert whole["pdf_page_count"] == 2
    assert whole["complete_source_coverage"] is True
    assert whole["status"] == "VISUAL_CHECK_REQUIRED"
    assert whole["visual_check_pages"] == [2]
    assert whole["pages"][0]["pdf_page"] == 1
    assert whole["source_size_bytes"] == path.stat().st_size

    bounded = inspect_pdf(path, start_page=1, end_page=1,
                          expected_sha256=whole["source_sha256"])
    assert bounded["complete_source_coverage"] is False
    assert bounded["status"] == "TEXT_PRESENT"
    assert [page["pdf_page"] for page in bounded["pages"]] == [1]


def test_preflight_fails_closed_on_source_mismatch_or_invalid_range(tmp_path: Path):
    path = tmp_path / "source.pdf"
    _pdf(path)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        inspect_pdf(path, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="size mismatch"):
        inspect_pdf(path, expected_size=1)
    with pytest.raises(ValueError, match="outside the source"):
        inspect_pdf(path, start_page=2, end_page=3)


def test_image_only_page_is_visual_check_not_native_evidence(tmp_path: Path):
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
    path = tmp_path / "scan.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_image(fitz.Rect(72, 72, 112, 112), pixmap=image)
        doc.save(path)

    report = inspect_pdf(path)
    assert report["pages"][0]["native_text_chars"] == 0
    assert report["visual_check_pages"] == [1]
    assert report["status"] == "VISUAL_CHECK_REQUIRED"


def test_non_pdf_bytes_with_pdf_suffix_are_rejected(tmp_path: Path):
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
    path = tmp_path / "renamed.pdf"
    path.write_bytes(image.tobytes("png"))
    with pytest.raises(ValueError, match="not a PDF"):
        inspect_pdf(path)


def test_cli_never_overwrites_source_even_via_alias(tmp_path: Path, monkeypatch):
    path = tmp_path / "source.pdf"
    _pdf(path)
    original = path.read_bytes()
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    for output in (path, alias):
        monkeypatch.setattr(sys, "argv", ["mls-pdf-preflight", str(path), "--output", str(output)])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
        assert path.read_bytes() == original
