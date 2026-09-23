from __future__ import annotations

import argparse
import json
from pathlib import Path

from medical_learning_system.source_catalog import SourceCatalog
from medical_learning_system.supabase_source_map import SupabaseSourceMapStore
from medical_learning_system.supabase_storage import build_supabase_client


DEFAULT_CATALOG = Path("data/sources/core_library.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync the canonical logical Book Registry into Supabase."
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="Path to the logical source catalog YAML.",
    )
    args = parser.parse_args()

    catalog = SourceCatalog.load(args.catalog)
    store = SupabaseSourceMapStore(build_supabase_client())
    count = store.upsert_catalog(catalog)
    print(
        json.dumps(
            {
                "catalog": str(args.catalog),
                "logical_sources_upserted": count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
