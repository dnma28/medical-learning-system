from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .blueprint import Hoc90Blueprint
from .session import Hoc90Session, SessionStatus, SourceSpineRef


class BootstrapMode(str, Enum):
    RESUME = "resume"
    START_NEW = "start_new"
    NEEDS_CURRICULUM = "needs_curriculum"
    NEEDS_BLUEPRINT = "needs_blueprint"


class Hoc90Command(str, Enum):
    START = "start"
    CONTINUE = "continue"


class BootstrapPlan(BaseModel):
    mode: BootstrapMode
    session_id: str | None = None
    curriculum_position: str | None = None
    source_spine: list[SourceSpineRef] = Field(default_factory=list)
    retrieval_targets: list[str] = Field(default_factory=list)
    open_error_ids: list[str] = Field(default_factory=list)
    resume_question_id: str | None = None
    resume_hint_level: int = 0
    reason: str


def build_bootstrap_plan(
    *,
    command: Hoc90Command,
    resumable_session: Hoc90Session | None,
    active_blueprint: Hoc90Blueprint | None,
    approved_curriculum_position: str | None,
) -> BootstrapPlan:
    """Resolve the minimum HỌC90 start path without scanning the full project."""

    if resumable_session is not None and resumable_session.status in {
        SessionStatus.ACTIVE,
        SessionStatus.PAUSED,
    }:
        checkpoint = resumable_session.checkpoint
        refs = [
            item
            for item in resumable_session.source_spine
            if isinstance(item, SourceSpineRef)
        ]
        return BootstrapPlan(
            mode=BootstrapMode.RESUME,
            session_id=resumable_session.session_id,
            curriculum_position=resumable_session.curriculum_position,
            source_spine=refs,
            resume_question_id=checkpoint.question_id if checkpoint else None,
            resume_hint_level=checkpoint.hint_level if checkpoint else 0,
            reason=(
                "Resume the unfinished HỌC90 session before creating a new session."
            ),
        )

    if command == Hoc90Command.CONTINUE:
        return BootstrapPlan(
            mode=BootstrapMode.NEEDS_BLUEPRINT,
            reason="No resumable HỌC90 session exists.",
        )

    if not approved_curriculum_position:
        return BootstrapPlan(
            mode=BootstrapMode.NEEDS_CURRICULUM,
            reason=(
                "A new session requires a learner-approved curriculum position; "
                "the runtime must not invent a large curriculum change."
            ),
        )

    if active_blueprint is None:
        return BootstrapPlan(
            mode=BootstrapMode.NEEDS_BLUEPRINT,
            curriculum_position=approved_curriculum_position,
            reason=(
                "The curriculum position is approved but no active dynamic "
                "HỌC90 blueprint is available yet."
            ),
        )

    return BootstrapPlan(
        mode=BootstrapMode.START_NEW,
        curriculum_position=active_blueprint.curriculum_position,
        source_spine=active_blueprint.source_spine,
        retrieval_targets=active_blueprint.retrieval_targets,
        open_error_ids=active_blueprint.open_error_ids,
        reason=(
            "Start from the active blueprint using only its source targets, "
            "learner-state retrieval targets, and approved curriculum position."
        ),
    )
