from __future__ import annotations

import argparse
import json
from pathlib import Path

from medical_learning_system.book_compile import compile_book_from_pdf
from medical_learning_system.drive_source import GoogleDriveSourceFetcher, build_google_drive_service


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile one Source Map review packet and finite exception queue."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--drive-file-id")
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/source-map-batch"))
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--logical-source-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--provider-file-id")
    parser.add_argument("--binding-state", required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-size", type=int)
    parser.add_argument("--allow-page-ranges", action="store_true")
    parser.add_argument("--allowed-disposition", action="append", default=[])
    return parser


def main() -> None:
    args = _parser().parse_args()
    pdf_path = args.pdf
    provider_file_id = args.provider_file_id or args.drive_file_id
    if pdf_path is None:
        fetcher = GoogleDriveSourceFetcher(build_google_drive_service())
        pdf_path = fetcher.cache_pdf(
            args.drive_file_id,
            cache_dir=args.cache_dir / "sources",
        )

    _, report = compile_book_from_pdf(
        manifest_path=args.manifest,
        pdf_path=pdf_path,
        packet_path=args.packet,
        report_path=args.report,
        cache_dir=args.cache_dir,
        batch_id=args.batch_id,
        logical_source_id=args.logical_source_id,
        source_id=args.source_id,
        provider_file_id=provider_file_id,
        binding_state=args.binding_state,
        expected_sha256=args.expected_sha256,
        expected_size=args.expected_size,
        point_locator_only=not args.allow_page_ranges,
        allowed_dispositions=args.allowed_disposition,
    )
    print(json.dumps({
        "status": "COMPILED",
        "batch_id": report.batch_id,
        "work_key": report.work_key,
        "total_rows": report.total_rows,
        "evidence_matched_rows": report.evidence_matched_rows,
        "evidence_exception_rows": report.evidence_exception_rows,
        "structural_review_rows": report.structural_review_rows,
        "review_exception_rows": report.review_exception_rows,
        "next_gate": report.next_gate,
        "publish_authorized": report.publish_authorized,
        "packet": str(args.packet),
        "report": str(args.report),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
