import pytest

from medical_learning_system.hoc90.blueprint import (
    BlueprintStatus,
    Hoc90Blueprint,
)
from medical_learning_system.hoc90.bootstrap import BootstrapMode, Hoc90Command
from medical_learning_system.hoc90.runtime_service import (
    Hoc90BootstrapError,
    Hoc90RuntimeService,
)
from medical_learning_system.hoc90.session import (
    Hoc90Session,
    SessionCheckpoint,
    SessionStage,
    SessionStatus,
    SourceSpineRef,
)


def source_ref() -> SourceSpineRef:
    return SourceSpineRef(
        logical_source_id="costanzo-physiology",
        source_map_node_id="costanzo-physiology:outline:0007",
        source_id="costanzo-physical",
        source_anchor={"pdf_page": 8},
        learning_value=None,
    )


def blueprint(position="physiology/costanzo/ch1/body-fluids") -> Hoc90Blueprint:
    return Hoc90Blueprint(
        lesson_id="lesson-1",
        status=BlueprintStatus.ACTIVE,
        curriculum_position=position,
        source_spine=[source_ref()],
        learning_objectives=["Explain the source-grounded ICF/ECF partition."],
        completion_gate=["Independent retrieval."],
    )


def session(status=SessionStatus.PAUSED) -> Hoc90Session:
    return Hoc90Session(
        session_id="session-1",
        topic="Body fluids",
        target_outcome="Retrieve the source-grounded relationship.",
        status=status,
        curriculum_position="physiology/costanzo/ch1/body-fluids",
        source_spine=[source_ref()],
        toc_position="costanzo-physiology:outline:0007",
        checkpoint=SessionCheckpoint(
            source_ref=source_ref(),
            toc_position="costanzo-physiology:outline:0007",
        ),
        stages=[
            SessionStage(name="whole", minutes=90, objective="test"),
        ],
    )


class Store:
    def __init__(self, *, resumable=None, active_blueprint=None):
        self.resumable = resumable
        self.active_blueprint = active_blueprint
        self.saved = []

    def load_resumable_session(self):
        return self.resumable

    def get_active_blueprint(self):
        return self.active_blueprint

    def save_session(self, value):
        self.saved.append(value)
        self.resumable = value
        return value


def test_start_resumes_existing_paused_session_before_creating_anything():
    store = Store(resumable=session(), active_blueprint=blueprint())
    result = Hoc90RuntimeService(store).bootstrap(
        Hoc90Command.START,
        approved_curriculum_position="physiology/costanzo/ch1/body-fluids",
    )

    assert result.plan.mode == BootstrapMode.RESUME
    assert result.created is False
    assert result.resumed is True
    assert result.session is not None
    assert result.session.status == SessionStatus.ACTIVE
    assert len(store.saved) == 1


def test_continue_resumes_existing_active_session_without_rewrite():
    existing = session(SessionStatus.ACTIVE)
    store = Store(resumable=existing, active_blueprint=blueprint())

    result = Hoc90RuntimeService(store).bootstrap(Hoc90Command.CONTINUE)

    assert result.plan.mode == BootstrapMode.RESUME
    assert result.session == existing
    assert result.resumed is True
    assert store.saved == []


def test_continue_without_resumable_session_does_not_create_one():
    store = Store(active_blueprint=blueprint())

    result = Hoc90RuntimeService(store).bootstrap(Hoc90Command.CONTINUE)

    assert result.plan.mode == BootstrapMode.NEEDS_BLUEPRINT
    assert result.session is None
    assert store.saved == []


def test_start_without_approved_position_fails_closed_to_curriculum():
    store = Store(active_blueprint=blueprint())

    result = Hoc90RuntimeService(store).bootstrap(Hoc90Command.START)

    assert result.plan.mode == BootstrapMode.NEEDS_CURRICULUM
    assert result.session is None


def test_start_with_approved_position_but_no_blueprint_needs_blueprint():
    store = Store()

    result = Hoc90RuntimeService(store).bootstrap(
        Hoc90Command.START,
        approved_curriculum_position="physiology/costanzo/ch1/body-fluids",
    )

    assert result.plan.mode == BootstrapMode.NEEDS_BLUEPRINT
    assert result.session is None


def test_start_creates_active_90_minute_session_from_matching_blueprint():
    bp = blueprint()
    store = Store(active_blueprint=bp)

    result = Hoc90RuntimeService(store).bootstrap(
        Hoc90Command.START,
        approved_curriculum_position=bp.curriculum_position,
    )

    assert result.plan.mode == BootstrapMode.START_NEW
    assert result.created is True
    assert result.session is not None
    assert result.session.status == SessionStatus.ACTIVE
    assert result.session.is_90_minutes() is True
    assert result.session.curriculum_position == bp.curriculum_position
    assert result.session.primary_source_ref() == bp.primary_source
    assert result.session.primary_source_ref().learning_value is None
    assert result.session.checkpoint is not None
    assert result.session.checkpoint.source_ref == bp.primary_source
    assert len(store.saved) == 1


def test_start_rejects_active_blueprint_for_different_approved_position():
    store = Store(active_blueprint=blueprint("position-a"))

    with pytest.raises(Hoc90BootstrapError, match="does not match"):
        Hoc90RuntimeService(store).bootstrap(
            Hoc90Command.START,
            approved_curriculum_position="position-b",
        )

    assert store.saved == []
