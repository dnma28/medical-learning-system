from types import SimpleNamespace

import pytest

from medical_learning_system.hoc90 import (
    Hoc90TurnResolution,
    check_hoc90_readiness,
)
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
from medical_learning_system.hoc90.source_context import (
    ResolvedSourceContext,
    SourceContextErrorCode,
    SourceContextUnavailable,
)
from medical_learning_system.learning.router import AdaptiveAction, QualityMode
from medical_learning_system.source_map import LearningValue
from medical_learning_system.supabase_storage import supabase_data


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
    def __init__(
        self,
        *,
        resumable=None,
        active_blueprint=None,
        due_concepts=None,
        open_errors=None,
    ):
        self.resumable = resumable
        self.active_blueprint = active_blueprint
        self.due_concepts = list(due_concepts or [])
        self.open_errors = list(open_errors or [])
        self.saved = []

    def load_resumable_session(self):
        return self.resumable

    def get_session(self, session_id):
        if self.resumable and self.resumable.session_id == session_id:
            return self.resumable
        return None

    def get_active_blueprint(self):
        return self.active_blueprint

    def save_session(self, value):
        self.saved.append(value)
        self.resumable = value
        return value

    def list_due_retrieval_concept_ids(self, *, as_of=None, limit=20):
        return self.due_concepts[:limit]

    def list_open_errors(self, *, concept_id=None):
        return [
            SimpleNamespace(id=err_id, concept_id=concept_id)
            for err_id in self.open_errors
        ]


class StaticResolver:
    def __init__(self, *, passages=None, error=None):
        self.passages = list(passages or ["Verified Costanzo ICF/ECF passage."])
        self.error = error

    def resolve(self, ref: SourceSpineRef) -> ResolvedSourceContext:
        if self.error is not None:
            raise self.error
        return ResolvedSourceContext(
            source_ref=ref,
            evidence_ids=["ev-costanzo-1"],
            passages=self.passages,
            page_start=8,
            page_end=8,
        )


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


@pytest.mark.parametrize("command", [Hoc90Command.START, Hoc90Command.CONTINUE])
@pytest.mark.parametrize("status", [SessionStatus.ACTIVE, SessionStatus.PAUSED])
def test_historical_resume_returns_existing_branch_errors_and_unknown_goals(command, status):
    row = session(status).model_dump(mode="json")
    row["stages"][0].pop("objective")
    row["checkpoint"].update({
        "question_id": "question-existing", "hint_level": 2,
        "current_branch": "repair-existing", "open_error_ids": ["error-existing"],
    })
    existing = Hoc90Session.from_persisted(row)
    store = Store(resumable=existing, active_blueprint=blueprint("different-position"))

    result = Hoc90RuntimeService(store).bootstrap(command)

    assert result.plan.mode == BootstrapMode.RESUME
    assert result.plan.session_id == existing.session_id
    assert result.plan.resume_question_id == "question-existing"
    assert result.plan.resume_hint_level == 2
    assert result.plan.resume_branch == "repair-existing"
    assert result.plan.open_error_ids == ["error-existing"]
    assert result.plan.source_spine == [existing.primary_source_ref()]
    assert result.session.stages[0].objective is None
    assert result.session.checkpoint == existing.checkpoint
    assert len(store.saved) == (1 if status == SessionStatus.PAUSED else 0)


def test_continue_without_resumable_session_does_not_create_one():
    store = Store(active_blueprint=blueprint())

    result = Hoc90RuntimeService(store).bootstrap(Hoc90Command.CONTINUE)

    assert result.plan.mode == BootstrapMode.NEEDS_BLUEPRINT
    assert result.session is None
    assert store.saved == []


def test_start_reuses_curriculum_position_from_active_blueprint():
    bp = blueprint()
    store = Store(active_blueprint=bp)

    result = Hoc90RuntimeService(store).bootstrap(Hoc90Command.START)

    assert result.plan.mode == BootstrapMode.START_NEW
    assert result.created is True
    assert result.session is not None
    assert result.session.curriculum_position == bp.curriculum_position


def test_start_without_blueprint_or_explicit_position_needs_curriculum():
    store = Store()

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


def test_existing_paused_session_wins_over_new_start_approval_mismatch():
    store = Store(
        resumable=session(),
        active_blueprint=blueprint("new-position"),
    )

    result = Hoc90RuntimeService(store).bootstrap(
        Hoc90Command.START,
        approved_curriculum_position="different-new-position",
    )

    assert result.plan.mode == BootstrapMode.RESUME
    assert result.resumed is True
    assert result.session is not None
    assert result.session.status == SessionStatus.ACTIVE


def test_resolve_turn_hydrates_due_retrieval_at_session_start():
    bp = blueprint()
    store = Store(
        active_blueprint=bp,
        due_concepts=["osmolarity-vs-tonicity"],
    )
    service = Hoc90RuntimeService(store)
    boot = service.bootstrap(Hoc90Command.START)

    turn = service.resolve_turn(
        session=boot.session,
        source_context_resolver=StaticResolver(),
    )

    assert isinstance(turn, Hoc90TurnResolution)
    assert turn.routing_context.session_start is True
    assert turn.decision.action == AdaptiveAction.START_RETRIEVAL
    assert turn.decision.target_ids == ["osmolarity-vs-tonicity"]
    assert turn.source_context is not None
    assert turn.source_context.passages == ["Verified Costanzo ICF/ECF passage."]


def test_resolve_turn_routes_source_gap_to_source_recovery_fail_closed():
    active = session(SessionStatus.ACTIVE)
    store = Store(resumable=active)
    resolver = StaticResolver(
        error=SourceContextUnavailable(
            "No promoted evidence link exists for node.",
            code=SourceContextErrorCode.SOURCE_GAP,
        )
    )

    turn = Hoc90RuntimeService(store).resolve_turn(
        session_id="session-1",
        source_context_resolver=resolver,
    )

    assert turn.source_context is None
    assert turn.source_error_code == SourceContextErrorCode.SOURCE_GAP
    assert turn.routing_context.source_gap is True
    assert turn.decision.action == AdaptiveAction.SOURCE_RECOVERY
    assert turn.decision.quality_mode == QualityMode.DEEP


def test_resolve_turn_merges_checkpoint_and_store_open_errors():
    active = session(SessionStatus.ACTIVE)
    active = active.pause(
        SessionCheckpoint(
            concept_id="starling-forces",
            source_ref=source_ref(),
            open_error_ids=["err-checkpoint"],
        )
    ).resume()
    store = Store(resumable=active, open_errors=["err-store", "err-checkpoint"])

    turn = Hoc90RuntimeService(store).resolve_turn(
        source_context_resolver=StaticResolver(),
    )

    assert turn.routing_context.open_error_ids == ["err-checkpoint", "err-store"]
    assert turn.decision.action == AdaptiveAction.ERROR_REMEDIATION
    assert turn.decision.target_ids == ["err-checkpoint", "err-store"]


def test_resolve_turn_enforces_freshness_gate_for_current_clinical_check():
    clinical_ref = SourceSpineRef(
        logical_source_id="katzung-basic-clinical-pharmacology",
        source_map_node_id="katzung:ch10:dosing",
        source_id="katzung-physical",
        source_anchor={"pdf_page": 150},
        learning_value=LearningValue.CURRENT_CLINICAL_CHECK,
        freshness_required=True,
    )
    clinical_session = session(SessionStatus.ACTIVE).pause(
        SessionCheckpoint(source_ref=clinical_ref)
    ).resume()
    store = Store(resumable=clinical_session)

    turn = Hoc90RuntimeService(store).resolve_turn(
        source_context_resolver=StaticResolver(),
        freshness_verified=False,
    )

    assert turn.decision.action == AdaptiveAction.VERIFY_CURRENT_EVIDENCE
    assert turn.decision.quality_mode == QualityMode.CRITICAL


def test_supabase_data_normalizes_object_and_dict_responses():
    obj_resp = SimpleNamespace(data=[{"id": "1"}])
    dict_resp = {"data": [{"id": "2"}]}
    empty_resp = SimpleNamespace(data=None)

    assert supabase_data(obj_resp) == [{"id": "1"}]
    assert supabase_data(dict_resp) == [{"id": "2"}]
    assert supabase_data(empty_resp) == []
    assert callable(check_hoc90_readiness)
