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
from medical_learning_system.supabase_storage import build_supabase_client


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
        required=True,
        choices=[action.value for action in AdaptiveAction],
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


def _rows(response):
    return list(getattr(response, "data", None) or [])


def _readiness(client, logical_source_id: str | None) -> dict[str, object]:
    blueprint_rows = _rows(
        client.table("mls_hoc90_blueprints")
        .select("lesson_id,status,curriculum_position,updated_at")
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    session_rows = _rows(
        client.table("mls_learning_sessions")
        .select("session_id,status,topic,updated_at")
        .in_("status", ["active", "paused"])
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    source = None
    source_map_readiness = None
    if logical_source_id:
        rows = _rows(
            client.table("mls_logical_sources")
            .select(
                "logical_source_id,title,source_map_state,source_map_version,"
                "promoted_staging_version"
            )
            .eq("logical_source_id", logical_source_id)
            .limit(1)
            .execute()
        )
        source = rows[0] if rows else None
        readiness_response = client.rpc(
            "mls_source_map_readiness",
            {"p_logical_source_id": logical_source_id},
        ).execute()
        raw_readiness = getattr(readiness_response, "data", None)
        if isinstance(raw_readiness, dict):
            source_map_readiness = raw_readiness
        elif (
            isinstance(raw_readiness, list)
            and raw_readiness
            and isinstance(raw_readiness[0], dict)
        ):
            source_map_readiness = raw_readiness[0]

    # Readiness is source-specific and version-specific. A few derived links do
    # not make a book runnable until the per-book evidence migration gate is ready.
    evidence_status = None
    if logical_source_id and source and source.get("promoted_staging_version") is not None:
        staging_version = int(source["promoted_staging_version"])
        status_rows = _rows(
            client.table("mls_source_map_evidence_status")
            .select("state,staging_version,evidence_blocks,promoted_links")
            .eq("logical_source_id", logical_source_id)
            .eq("staging_version", staging_version)
            .limit(1)
            .execute()
        )
        evidence_status = status_rows[0] if status_rows else None
        evidence_query = (
            client.table("mls_source_map_evidence_links")
            .select("evidence_id", count="exact")
            .eq("logical_source_id", logical_source_id)
            .eq("staging_version", staging_version)
            .eq("status", "promoted")
            .limit(1)
            .execute()
        )
    elif logical_source_id:
        evidence_query = (
            client.table("mls_source_map_evidence_links")
            .select("evidence_id", count="exact")
            .eq("logical_source_id", logical_source_id)
            .eq("status", "promoted")
            .limit(1)
            .execute()
        )
    else:
        evidence_query = (
            client.table("mls_evidence_blocks")
            .select("evidence_id", count="exact")
            .limit(1)
            .execute()
        )
    evidence_count = getattr(evidence_query, "count", None)
    if evidence_count is None:
        evidence_count = len(_rows(evidence_query))

    blockers: list[str] = []
    if not blueprint_rows:
        blockers.append("no_active_blueprint")
    if not session_rows:
        blockers.append("no_active_or_paused_session")
    if logical_source_id and (
        evidence_status is None or evidence_status.get("state") != "ready"
    ):
        blockers.append("source_map_evidence_not_ready")
    elif not evidence_count:
        blockers.append("no_exact_source_map_evidence")
    if logical_source_id and (
        source is None
        or source_map_readiness is None
        or source_map_readiness.get("ready_for_hoc90") is not True
    ):
        blockers.append("source_map_not_ready_for_hoc90")

    return {
        "ready": not blockers,
        "blockers": blockers,
        "active_blueprint": blueprint_rows[0] if blueprint_rows else None,
        "resumable_session": session_rows[0] if session_rows else None,
        "evidence_blocks": evidence_count,
        "source_map_evidence_status": evidence_status,
        "logical_source": source,
        "source_map_readiness": source_map_readiness,
    }


async def _prepare(args, client) -> dict[str, object]:
    store = SupabaseLearningStateStore(client)
    session = store.get_session(args.session_id)
    if session is None:
        raise SystemExit(f"Unknown HỌC90 session: {args.session_id}")
    source_ref = session.primary_source_ref()
    if source_ref is None:
        raise SystemExit("Session has no structured primary SourceSpineRef.")

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
