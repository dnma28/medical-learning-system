from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from ..learning.router import (
    LearningRouter,
    RoutingContext,
    RoutingDecision,
)
from ..supabase_storage import supabase_data as _rows
from .blueprint import Hoc90Blueprint
from .bootstrap import (
    BootstrapMode,
    BootstrapPlan,
    Hoc90Command,
    build_bootstrap_plan,
)
from .session import (
    Hoc90Session,
    SessionCheckpoint,
    SessionStage,
    SessionStatus,
    SourceSpineRef,
)
from .source_context import (
    ResolvedSourceContext,
    SourceContextErrorCode,
    SourceContextResolver,
    SourceContextUnavailable,
)


class Hoc90RuntimeStore(Protocol):
    def load_resumable_session(self) -> Hoc90Session | None: ...

    def get_active_blueprint(self) -> Hoc90Blueprint | None: ...

    def save_session(self, session: Hoc90Session) -> Hoc90Session: ...


class Hoc90BootstrapError(RuntimeError):
    """Raised when runtime state would require an unsafe inferred choice."""


class Hoc90BootstrapResult(BaseModel):
    plan: BootstrapPlan
    session: Hoc90Session | None = None
    created: bool = False
    resumed: bool = False


class Hoc90TurnResolution(BaseModel):
    """Canonical single-turn HỌC90 resolution: session -> source -> route -> context."""

    session: Hoc90Session
    source_ref: SourceSpineRef | None = None
    routing_context: RoutingContext
    decision: RoutingDecision
    source_context: ResolvedSourceContext | None = None
    source_error_code: SourceContextErrorCode | None = None
    source_error_message: str | None = None


class Hoc90RuntimeService:
    """Operational HỌC90 START/CONTINUE and single-turn orchestration.

    This service only coordinates already-approved runtime state. It never chooses
    a curriculum position, generates a blueprint, evaluates learner performance,
    or grants mastery.
    """

    def __init__(self, store: Hoc90RuntimeStore):
        self.store = store

    def bootstrap(
        self,
        command: Hoc90Command,
        *,
        approved_curriculum_position: str | None = None,
    ) -> Hoc90BootstrapResult:
        resumable = self.store.load_resumable_session()
        active_blueprint = self.store.get_active_blueprint()

        # ACTIVE is the persisted runtime state of an already-approved blueprint.
        # Requiring the learner to repeat its curriculum position on every START
        # would defeat the two-command interface. An explicit caller-supplied
        # position still acts as a stricter assertion and must match.
        effective_approved_position = approved_curriculum_position
        if (
            effective_approved_position is None
            and active_blueprint is not None
            and active_blueprint.curriculum_position
        ):
            effective_approved_position = active_blueprint.curriculum_position

        plan = build_bootstrap_plan(
            command=command,
            resumable_session=resumable,
            active_blueprint=active_blueprint,
            approved_curriculum_position=effective_approved_position,
        )

        if plan.mode == BootstrapMode.RESUME:
            if resumable is None:
                raise Hoc90BootstrapError(
                    "Bootstrap planner returned RESUME without a resumable session."
                )
            session = (
                resumable.resume()
                if resumable.status == SessionStatus.PAUSED
                else resumable
            )
            if session is not resumable:
                self.store.save_session(session)
            return Hoc90BootstrapResult(
                plan=plan,
                session=session,
                created=False,
                resumed=True,
            )

        if plan.mode != BootstrapMode.START_NEW:
            return Hoc90BootstrapResult(plan=plan)

        if (
            command == Hoc90Command.START
            and approved_curriculum_position
            and active_blueprint is not None
            and active_blueprint.curriculum_position != approved_curriculum_position
        ):
            raise Hoc90BootstrapError(
                "Active HỌC90 blueprint does not match the explicitly approved "
                "curriculum position."
            )

        if active_blueprint is None:
            raise Hoc90BootstrapError(
                "Bootstrap planner returned START_NEW without an active blueprint."
            )

        session = _session_from_blueprint(active_blueprint).start()
        self.store.save_session(session)
        return Hoc90BootstrapResult(
            plan=plan,
            session=session,
            created=True,
            resumed=False,
        )

    def resolve_turn(
        self,
        *,
        session: Hoc90Session | None = None,
        session_id: str | None = None,
        source_context_resolver: SourceContextResolver | None = None,
        router: LearningRouter | None = None,
        session_start: bool | None = None,
        due_retrieval_concept_ids: list[str] | None = None,
        weak_required_prerequisite_ids: list[str] | None = None,
        open_error_ids: list[str] | None = None,
        learner_requested_reference_detail: bool = False,
        learner_requested_integration: bool = False,
        freshness_verified: bool = False,
        concept_is_complex: bool = False,
        source_is_insufficient_for_explanation: bool = False,
        ready_for_transfer: bool = False,
        as_of: datetime | None = None,
        due_limit: int = 20,
    ) -> Hoc90TurnResolution:
        """Resolve learner state, exact source evidence, and next routing decision."""
        active_session = self._resolve_session(session=session, session_id=session_id)
        checkpoint = active_session.checkpoint
        source_ref = (
            checkpoint.source_ref
            if checkpoint is not None and checkpoint.source_ref is not None
            else active_session.primary_source_ref()
        )

        is_session_start = (
            session_start
            if session_start is not None
            else (
                checkpoint is not None
                and checkpoint.current_branch == "session_start"
                and checkpoint.question_id is None
            )
        )

        merged_errors = self._resolve_open_error_ids(
            checkpoint=checkpoint,
            explicit_error_ids=open_error_ids,
        )

        resolved_source: ResolvedSourceContext | None = None
        source_error_code: SourceContextErrorCode | None = None
        source_error_message: str | None = None
        source_gap = False
        source_anchor_available = bool(
            source_ref is not None
            and source_ref.source_id
            and source_ref.source_map_node_id
        )

        if source_context_resolver is not None:
            if source_ref is None:
                source_anchor_available = False
                source_gap = True
                source_error_code = SourceContextErrorCode.INVALID_REFERENCE
                source_error_message = "Session has no structured SourceSpineRef."
            else:
                try:
                    resolved_source = source_context_resolver.resolve(source_ref)
                except SourceContextUnavailable as exc:
                    source_error_code = exc.code
                    source_error_message = str(exc)
                    source_gap = True
                    if exc.code == SourceContextErrorCode.INVALID_REFERENCE:
                        source_anchor_available = False

        routing_context = RoutingContext(
            session_start=is_session_start,
            source_spine=source_ref.routing_key if source_ref is not None else None,
            current_toc_item=(
                (checkpoint.toc_position if checkpoint and checkpoint.toc_position else None)
                or active_session.toc_position
                or (source_ref.source_map_node_id if source_ref is not None else None)
            ),
            current_learning_value=(
                source_ref.learning_value if source_ref is not None else None
            ),
            due_retrieval_concept_ids=list(due_retrieval_concept_ids or []),
            weak_required_prerequisite_ids=list(weak_required_prerequisite_ids or []),
            open_error_ids=merged_errors,
            source_gap=source_gap,
            source_anchor_available=source_anchor_available,
            learner_requested_reference_detail=learner_requested_reference_detail,
            learner_requested_integration=learner_requested_integration,
            freshness_required=(
                bool(source_ref.freshness_required) if source_ref is not None else False
            ),
            freshness_verified=freshness_verified,
            concept_is_complex=concept_is_complex,
            source_is_insufficient_for_explanation=source_is_insufficient_for_explanation,
            ready_for_transfer=ready_for_transfer,
        )

        active_router = router or LearningRouter()
        due_provider = getattr(self.store, "list_due_retrieval_concept_ids", None)
        if callable(due_provider):
            decision = active_router.route_next_from_state(
                routing_context,
                due_retrieval_provider=self.store,  # type: ignore[arg-type]
                as_of=as_of,
                due_limit=due_limit,
            )
            if is_session_start and not routing_context.due_retrieval_concept_ids:
                routing_context = routing_context.model_copy(
                    update={"due_retrieval_concept_ids": list(decision.target_ids)}
                    if decision.action.value == "start_retrieval"
                    else {}
                )
        else:
            decision = active_router.route_next(routing_context)

        return Hoc90TurnResolution(
            session=active_session,
            source_ref=source_ref,
            routing_context=routing_context,
            decision=decision,
            source_context=resolved_source,
            source_error_code=source_error_code,
            source_error_message=source_error_message,
        )

    def _resolve_session(
        self,
        *,
        session: Hoc90Session | None,
        session_id: str | None,
    ) -> Hoc90Session:
        if session is not None:
            return session
        if session_id is not None:
            getter = getattr(self.store, "get_session", None)
            if not callable(getter):
                raise Hoc90BootstrapError("Runtime store does not support get_session.")
            found = getter(session_id)
            if found is None:
                raise KeyError(f"Unknown HỌC90 session: {session_id}")
            return found
        resumable = self.store.load_resumable_session()
        if resumable is None:
            raise Hoc90BootstrapError("No active or paused HỌC90 session is available.")
        return resumable

    def _resolve_open_error_ids(
        self,
        *,
        checkpoint: SessionCheckpoint | None,
        explicit_error_ids: list[str] | None,
    ) -> list[str]:
        if explicit_error_ids is not None:
            return list(dict.fromkeys(explicit_error_ids))
        combined: list[str] = list(checkpoint.open_error_ids) if checkpoint else []
        list_errors = getattr(self.store, "list_open_errors", None)
        if callable(list_errors):
            concept_id = checkpoint.concept_id if checkpoint else None
            for item in list_errors(concept_id=concept_id):
                err_id = getattr(item, "id", None)
                if err_id:
                    combined.append(str(err_id))
        return list(dict.fromkeys(combined))


def check_hoc90_readiness(
    client: Any,
    logical_source_id: str | None = None,
) -> dict[str, object]:
    """Inspect live Supabase runtime readiness for HỌC90 and optional logical book."""
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
    evidence_status = None
    evidence_migration_history = False
    current_stage = None

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
        if source and source.get("promoted_staging_version") is not None:
            current_stage = int(source["promoted_staging_version"])

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

        history_rows = _rows(
            client.table("mls_source_map_evidence_status")
            .select(
                "state,staging_version,legacy_fallback_disabled,"
                "evidence_blocks,promoted_links"
            )
            .eq("logical_source_id", logical_source_id)
            .eq("legacy_fallback_disabled", True)
            .execute()
        )
        evidence_migration_history = bool(history_rows)
        if current_stage is not None:
            evidence_status = next(
                (
                    row
                    for row in history_rows
                    if int(row.get("staging_version") or -1) == current_stage
                ),
                None,
            )

    if logical_source_id and current_stage is not None:
        evidence_query = (
            client.table("mls_source_map_evidence_links")
            .select("evidence_id", count="exact")
            .eq("logical_source_id", logical_source_id)
            .eq("staging_version", current_stage)
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
        source is None
        or source_map_readiness is None
        or source_map_readiness.get("ready_for_hoc90") is not True
    ):
        blockers.append("source_map_not_ready_for_hoc90")

    if logical_source_id and evidence_migration_history and evidence_status is None:
        blockers.append("source_map_evidence_stale")
    elif evidence_status and evidence_status.get("state") == "review_required":
        blockers.append("source_map_evidence_review_required")
    elif evidence_status and evidence_status.get("state") == "stale":
        blockers.append("source_map_evidence_stale")
    elif not evidence_count:
        blockers.append("no_exact_source_map_evidence")

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


def _session_from_blueprint(blueprint: Hoc90Blueprint) -> Hoc90Session:
    primary = blueprint.primary_source
    target_outcome = (
        blueprint.learning_objectives[0]
        if blueprint.learning_objectives
        else "Complete the active source-grounded HỌC90 blueprint."
    )
    topic = (
        blueprint.integration_goal
        or blueprint.curriculum_position
        or primary.routing_key
    )
    return Hoc90Session(
        topic=topic,
        target_outcome=target_outcome,
        curriculum_position=blueprint.curriculum_position,
        source_spine=list(blueprint.source_spine),
        toc_position=primary.source_map_node_id,
        checkpoint=SessionCheckpoint(
            toc_position=primary.source_map_node_id,
            source_ref=primary,
            current_branch="session_start",
            return_to_source=primary.routing_key,
        ),
        stages=_default_stages(),
    )


def _default_stages() -> list[SessionStage]:
    return [
        SessionStage(
            name="retrieval",
            minutes=15,
            objective="Retrieve prior understanding before new teaching.",
        ),
        SessionStage(
            name="source_reasoning",
            minutes=25,
            objective="Reason from the active source spine with Socratic prompts.",
        ),
        SessionStage(
            name="self_explanation",
            minutes=20,
            objective="Explain the source relationships independently.",
        ),
        SessionStage(
            name="transfer",
            minutes=20,
            objective="Apply understanding to bounded transfer or counterfactual tasks.",
        ),
        SessionStage(
            name="consolidation",
            minutes=10,
            objective="Retest independently and save an evidence-based checkpoint.",
        ),
    ]
