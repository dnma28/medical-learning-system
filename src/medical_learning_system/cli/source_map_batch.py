from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from medical_learning_system.drive_source import GoogleDriveSourceFetcher, build_google_drive_service
from medical_learning_system.source_map_batch import (
    load_decisions,
    load_packet,
    prepare_from_pdf,
    validate_decisions,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and hard-validate bounded Source Map review batches."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--manifest", type=Path, required=True)
    source = prepare.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--drive-file-id")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--cache-dir", type=Path, default=Path(".cache/source-map-batch"))
    prepare.add_argument("--batch-id", required=True)
    prepare.add_argument("--logical-source-id", required=True)
    prepare.add_argument("--source-id", required=True)
    prepare.add_argument("--provider-file-id")
    prepare.add_argument("--binding-state", required=True)
    prepare.add_argument("--expected-sha256")
    prepare.add_argument("--expected-size", type=int)
    prepare.add_argument("--allow-page-ranges", action="store_true")
    prepare.add_argument("--allowed-disposition", action="append", default=[])

    validate = sub.add_parser("validate")
    validate.add_argument("--packet", type=Path, required=True)
    validate.add_argument("--decisions", type=Path, required=True)
    return parser


def _prepare(args: argparse.Namespace) -> None:
    kwargs = dict(
        manifest_path=args.manifest,
        output_path=args.output,
        cache_dir=args.cache_dir,
        batch_id=args.batch_id,
        logical_source_id=args.logical_source_id,
        source_id=args.source_id,
        provider_file_id=args.provider_file_id or args.drive_file_id,
        binding_state=args.binding_state,
        expected_sha256=args.expected_sha256,
        expected_size=args.expected_size,
        point_locator_only=not args.allow_page_ranges,
        allowed_dispositions=args.allowed_disposition,
    )
    if args.pdf is not None:
        packet = prepare_from_pdf(pdf_path=args.pdf, **kwargs)
    else:
        fetcher = GoogleDriveSourceFetcher(build_google_drive_service())
        with tempfile.TemporaryDirectory(prefix="mls-source-map-batch-") as directory:
            with fetcher.materialize_pdf(
                args.drive_file_id,
                directory=Path(directory),
            ) as pdf_path:
                packet = prepare_from_pdf(pdf_path=pdf_path, **kwargs)

    print(json.dumps({
        "status": "PREPARED",
        "batch_id": packet.batch_id,
        "rows": len(packet.rows),
        "source_sha256": packet.source.content_sha256,
        "source_pages": packet.source.page_count,
        "visual_review_rows": sum(
            bool(row.evidence.visual_required_reasons) for row in packet.rows
        ),
        "output": str(args.output),
    }, ensure_ascii=False))


def _validate(args: argparse.Namespace) -> None:
    packet = load_packet(args.packet)
    decisions = load_decisions(args.decisions)
    errors = validate_decisions(packet, decisions)
    result = {
        "status": "PASS" if not errors else "QA_GATE_FAILED",
        "batch_id": packet.batch_id,
        "rows": len(packet.rows),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(2)


def main() -> None:
    args = _parser().parse_args()
    if args.command == "prepare":
        _prepare(args)
    else:
        _validate(args)


if __name__ == "__main__":
    main()
