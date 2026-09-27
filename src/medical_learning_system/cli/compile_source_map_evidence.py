from __future__ import annotations

import argparse
import json

from medical_learning_system.drive_source import (
    GoogleDriveSourceFetcher,
    build_google_drive_service,
)
from medical_learning_system.source_map_evidence import (
    DriveSourceMapEvidenceCompiler,
    SupabaseSourceMapEvidenceCompiler,
)
from medical_learning_system.supabase_storage import (
    SupabaseMedicalStore,
    build_supabase_client,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile exact Drive PDF evidence against a promoted Source Map."
    )
    parser.add_argument("--logical-source-id", required=True)
    parser.add_argument("--source-id")
    parser.add_argument(
        "--allow-replace-existing",
        action="store_true",
        help="Explicitly replace existing evidence for the physical source.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    client = build_supabase_client()
    medical = SupabaseMedicalStore(client)

    if args.source_id:
        source = medical.get_source(args.source_id)
        if source is None:
            raise SystemExit(f"Unknown source_id: {args.source_id}")
    else:
        response = (
            client.table("mls_source_map_nodes")
            .select("source_id")
            .eq("logical_source_id", args.logical_source_id)
            .execute()
        )
        source_ids = sorted(
            {
                str(row["source_id"])
                for row in (getattr(response, "data", None) or [])
                if row.get("source_id")
            }
        )
        if len(source_ids) != 1:
            raise SystemExit(
                "Logical source uses multiple physical sources; pass --source-id explicitly."
            )
        source = medical.get_source(source_ids[0])
        if source is None:
            raise SystemExit(f"Unknown source_id: {source_ids[0]}")

    drive = build_google_drive_service()
    result = DriveSourceMapEvidenceCompiler(
        compiler=SupabaseSourceMapEvidenceCompiler(client),
        fetcher=GoogleDriveSourceFetcher(drive),
    ).compile_source(
        logical_source_id=args.logical_source_id,
        source=source,
        allow_replace_existing=args.allow_replace_existing,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
