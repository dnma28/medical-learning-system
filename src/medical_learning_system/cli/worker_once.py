from __future__ import annotations

import json
import sys

from medical_learning_system.drive_source import build_google_drive_service
from medical_learning_system.supabase_storage import build_supabase_client
from medical_learning_system.worker import (
    WorkerAction,
    build_supabase_drive_worker,
)


def main() -> None:
    client = build_supabase_client()
    drive_service = build_google_drive_service()
    outcome = build_supabase_drive_worker(
        client,
        drive_service,
    ).run_once()

    print(
        json.dumps(
            outcome.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        )
    )
    if outcome.action == WorkerAction.FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
