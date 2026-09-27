from __future__ import annotations

import argparse
import json

from medical_learning_system.hoc90.bootstrap import Hoc90Command
from medical_learning_system.hoc90.runtime_service import Hoc90RuntimeService
from medical_learning_system.supabase_learning_state import SupabaseLearningStateStore
from medical_learning_system.supabase_storage import build_supabase_client


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap HỌC90 START/CONTINUE from live learner runtime state."
    )
    parser.add_argument(
        "command",
        choices=[command.value for command in Hoc90Command],
    )
    parser.add_argument("--approved-curriculum-position")
    return parser


def main() -> None:
    args = _parser().parse_args()
    client = build_supabase_client()
    result = Hoc90RuntimeService(
        SupabaseLearningStateStore(client)
    ).bootstrap(
        Hoc90Command(args.command),
        approved_curriculum_position=args.approved_curriculum_position,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
