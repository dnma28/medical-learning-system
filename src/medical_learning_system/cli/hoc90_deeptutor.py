from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from medical_learning_system.deeptutor_runtime import DeepTutorReadingInput
from medical_learning_system.hoc90.deeptutor_bridge import (
    DeepTutorSubmission,
    Hoc90DeepTutorBridge,
)
from medical_learning_system.hoc90.runtime_service import (
    Hoc90RuntimeService,
    check_hoc90_readiness,
)
from medical_learning_system.hoc90.source_context import (
    SourceContextUnavailable,
    SupabaseHoc90SourceContextResolver,
)
from medical_learning_system.learning.router import (
    AdaptiveAction,
    QualityMode,
    RoutingDecision,
)
from medical_learning_system.supabase_learning_state import SupabaseLearningStateStore
from medical_learning_system.supabase_storage import (
    build_supabase_client,
    supabase_data as _rows,
)

_readiness = check_hoc90_readiness


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the deployed HỌC90 ↔ DeepTutor backend bridge."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    readiness = sub.add_parser("readiness")
    readiness.add_argument("--logical-source-id")

    prepare = sub.add_parser("prepare")
    prepare.add_argument("session_id")
    prepare.add_argument(
        "--action",
        required=False,
        choices=[action.value for action in AdaptiveAction],
        help="Optional explicit route action; if omitted, resolved deterministically via Hoc90RuntimeService.",
    )
    prepare.add_argument("--target-id", action="append", default=[])
    prepare.add_argument("--quiz", action="store_true")
    prepare.add_argument("--source-text-file", type=Path)
    prepare.add_argument("--locale", default="vi")

    submit = sub.add_parser("submit")
    submit.add_argument("session_id")
    submit.add_argument("interaction_id")
    group = submit.add_mutually_exclusive_group(required=True)
    group.add_argument("--response")
    group.add_argument("--question-id")
    submit.add_argument("--choice-index", type=int)

    return parser


async def _prepare(args, client) -> dict[str, object]:
    store = SupabaseLearningStateStore(client)
    session = store.get_session(args.session_id)
    if session is None:
        raise SystemExit(f"Unknown HỌC90 session: {args.session_id}")
    source_ref = (
        session.checkpoint.source_ref
        if session.checkpoint is not None and session.checkpoint.source_ref is not None
        else session.primary_source_ref()
    )
    if source_ref is None:
        raise SystemExit("Session has no structured primary SourceSpineRef.")

    if args.action is not None:
        if args.source_text_file:
            source_context = [args.source_text_file.read_text(encoding="utf-8")]
            page = source_ref.source_anchor.get("page_start")
        else:
            try:
                resolved = SupabaseHoc90SourceContextResolver(client).resolve(source_ref)
            except SourceContextUnavailable as exc:
                raise SystemExit(f"{exc.code.value}: {exc}") from exc
            source_context = resolved.passages
            page = resolved.page_start

        decision = RoutingDecision(
            action=AdaptiveAction(args.action),
            quality_mode=QualityMode.DEEP,
            reason="CLI bridge invocation using an already-resolved HỌC90 route.",
            target_ids=list(args.target_id),
            return_to_source_spine=source_ref.routing_key,
        )
    else:
        resolver = (
            None
            if args.source_text_file
            else SupabaseHoc90SourceContextResolver(client)
        )
        turn = Hoc90RuntimeService(store).resolve_turn(
            session=session,
            source_context_resolver=resolver,
        )
        if args.source_text_file:
            source_context = [args.source_text_file.read_text(encoding="utf-8")]
            page = source_ref.source_anchor.get("page_start")
        else:
            if turn.source_context is None:
                code = turn.source_error_code.value if turn.source_error_code else "SOURCE_GAP"
                raise SystemExit(f"{code}: {turn.source_error_message}")
            source_context = turn.source_context.passages
            page = turn.source_context.page_start

        decision = turn.decision
        if args.target_id:
            decision = decision.model_copy(update={"target_ids": list(args.target_id)})

    reading = DeepTutorReadingInput(
        material_id=source_ref.logical_source_id,
        locator=(int(page) + 1) if isinstance(page, int) and page >= 0 else 1,
        source_anchor=json.dumps(source_ref.source_anchor, ensure_ascii=False),
        locale=args.locale,
    )
    prepared = await Hoc90DeepTutorBridge(store=store).prepare(
        session_id=args.session_id,
        decision=decision,
        source_context=source_context,
        reading=reading,
        source_ref=source_ref,
        quiz=args.quiz,
    )
    return prepared.model_dump(mode="json")


def _submit(args, client) -> dict[str, object]:
    if args.question_id is not None and args.choice_index is None:
        raise SystemExit("--question-id requires --choice-index.")
    store = SupabaseLearningStateStore(client)
    submission = (
        DeepTutorSubmission(
            interaction_id=args.interaction_id,
            learner_response=args.response,
        )
        if args.response is not None
        else DeepTutorSubmission(
            interaction_id=args.interaction_id,
            question_id=args.question_id,
            selected_choice_index=args.choice_index,
        )
    )
    event = Hoc90DeepTutorBridge(store=store).submit(
        session_id=args.session_id,
        submission=submission,
    )
    return event.model_dump(mode="json")


def main() -> None:
    args = _parser().parse_args()
    client = build_supabase_client()

    if args.command == "readiness":
        result = _readiness(client, args.logical_source_id)
    elif args.command == "prepare":
        result = asyncio.run(_prepare(args, client))
    else:
        result = _submit(args, client)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
