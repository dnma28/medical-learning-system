from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

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


class Hoc90RuntimeService:
    """Operational HỌC90 START/CONTINUE orchestration.

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

        plan = build_bootstrap_plan(
            command=command,
            resumable_session=resumable,
            active_blueprint=active_blueprint,
            approved_curriculum_position=approved_curriculum_position,
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
