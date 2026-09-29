from __future__ import annotations

import argparse
import json
from pathlib import Path

from medical_learning_system.sources import sha256_file


def inspect_pdf(
    path: Path,
    *,
    start_page: int = 1,
    end_page: int | None = None,
    min_text_chars: int = 20,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
) -> dict:
    """Report physical-page text availability without treating it as verified evidence."""
    import fitz

    size = path.stat().st_size
    digest = sha256_file(path)
    if expected_size is not None and size != expected_size:
        raise ValueError(f"source size mismatch: expected {expected_size}, got {size}")
    if expected_sha256 is not None and digest.lower() != expected_sha256.lower():
        raise ValueError("source SHA-256 mismatch")
    if min_text_chars < 0:
        raise ValueError("min_text_chars must be nonnegative")

    with fitz.open(path) as pdf:
        if not pdf.is_pdf:
            raise ValueError("input is not a PDF")
        if pdf.needs_pass:
            raise ValueError("encrypted PDF needs a password")
        count = len(pdf)
        last = count if end_page is None else end_page
        if count == 0 or not 1 <= start_page <= last <= count:
            raise ValueError("physical PDF page range is outside the source")
        pages = []
        for number in range(start_page, last + 1):
            try:
                page = pdf[number - 1]
                chars = len(page.get_text("text").strip())
                pages.append({
                    "pdf_page": number,
                    "native_text_chars": chars,
                    "rotation": page.rotation,
                    "visual_check_required": chars < min_text_chars,
                })
            except Exception as exc:
                pages.append({"pdf_page": number, "read_error": type(exc).__name__})

    errors = [p["pdf_page"] for p in pages if "read_error" in p]
    visual = [p["pdf_page"] for p in pages if p.get("visual_check_required")]
    return {
        "format_version": 1,
        "source_sha256": digest,
        "source_size_bytes": size,
        "pdf_page_count": count,
        "parser": f"PyMuPDF {fitz.VersionBind}",
        "inspected_pdf_pages": [start_page, last],
        "complete_source_coverage": start_page == 1 and last == count,
        "min_text_chars_heuristic": min_text_chars,
        "visual_check_pages": visual,
        "read_error_pages": errors,
        "status": "READ_ERROR" if errors else "VISUAL_CHECK_REQUIRED" if visual else "TEXT_PRESENT",
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only physical-page PDF intake preflight")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--min-text-chars", type=int, default=20)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-size", type=int)
    args = parser.parse_args()
    report = inspect_pdf(
        args.pdf,
        start_page=args.start_page,
        end_page=args.end_page,
        min_text_chars=args.min_text_chars,
        expected_sha256=args.expected_sha256,
        expected_size=args.expected_size,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "status", "source_sha256", "pdf_page_count", "inspected_pdf_pages",
        "complete_source_coverage", "visual_check_pages", "read_error_pages"
    )}))
    if report["read_error_pages"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
