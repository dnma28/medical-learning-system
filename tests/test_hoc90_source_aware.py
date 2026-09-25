import pytest

from medical_learning_system.hoc90.blueprint import (
    BlueprintStatus,
    Hoc90Blueprint,
    MasteryTarget,
    StudyMode,
)
from medical_learning_system.hoc90.bootstrap import (
    BootstrapMode,
    Hoc90Command,
    build_bootstrap_plan,
)
from medical_learning_system.hoc90.session import (
    Hoc90Session,
    SessionCheckpoint,
    SessionStage,
    SourceSpineRef,
)
from medical_learning_system.learning.router import (
    AdaptiveAction,
    LearningRouter,
    QualityMode,
    RoutingContext,
)
from medical_learning_system.source_map import LearningValue
from medical_learning_system.supabase_learning_state import (
    SupabaseLearningStateStore,
)


class Response:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.mode = "select"
        self.payload = None
        self.filters = []
        self.order_field = None
        self.order_desc = False
        self.limit_count = None
        self.conflict = []

    def select(self, _fields):
        self.mode = "select"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def update(self, payload):
        self.mode = "update"
        self.payload = payload
        return self

    def upsert(self, payload, on_conflict=""):
        self.mode = "upsert"
        self.payload = payload
        self.conflict = [x for x in on_conflict.split(",") if x]
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        matched = [
            row
            for row in rows
            if all(row.get(field) == value for field, value in self.filters)
        ]

        if self.mode == "update":
            for row in matched:
                row.update(self.payload)
            return Response(matched)

        if self.mode == "upsert":
            existing = next(
                (
                    row
                    for row in rows
                    if self.conflict
                    and all(
                        row.get(key) == self.payload.get(key)
                        for key in self.conflict
                    )
                ),
                None,
            )
            if existing is None:
                rows.append(dict(self.payload))
                existing = rows[-1]
            else:
                existing.update(self.payload)
            return Response([dict(existing)])

        if self.order_field:
            matched.sort(
                key=lambda row: row.get(self.order_field),
                reverse=self.order_desc,
            )
        if self.limit_count is not None:
            matched = matched[: self.limit_count
            ]
        return Response([dict(row) for row in matched])


class FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return FakeQuery(self, name)


def source_ref(**updates):
    data = {
        "logical_source_id": "costanzo-physiology",
        "source_map_node_id": "ch1-membrane-potential",
        "source_id": "costanzo-physiology--physical",
        "source_anchor": {"page_start": 12},
        "learning_value": LearningValue.CORE_MASTERY,
    }
    data.update(updates)
    return SourceSpineRef(**data)


def blueprint(**updates):
    data = {
        "lesson_id": "hoc90-001",
        "status": BlueprintStatus.ACTIVE,
        "curriculum_position": "foundation/membrane",
        "source_spine": [source_ref()],
        "learning_objectives": ["Giải thích điện thế màng từ gradient điện hóa."],
        "mastery_targets": [
            MasteryTarget(
                concept_id="electrochemical-gradient",
                target_level="M3",
                evidence_required=["mechanism", "counterfactual"],
            )
        ],
        "retrieval_targets": ["na-k-atpase"],
        "completion_gate": ["mechanism", "counterfactual", "transfer"],
        "return_to_source_spine": (
            "costanzo-physiology:ch1-membrane-potential"
        ),
    }
    data.update(updates)
    return Hoc90Blueprint(**data)


def session():
    return Hoc90Session(
        topic="Điện thế màng",
        target_outcome="Giải thích cơ chế điện thế nghỉ",
        curriculum_position="foundation/membrane",
        source_spine=[source_ref()],
        stages=[
            SessionStage(name="retrieval", minutes=10, objective="Recall"),
            SessionStage(name="mechanism", minutes=55, objective="Reason"),
            SessionStage(name="transfer", minutes=25, objective="Apply"),
        ],
    )


def test_blueprint_requires_freshness_for_current_clinical_target():
    clinical = source_ref(
        logical_source_id="katzung-basic-clinical-pharmacology",
        source_map_node_id="dose",
        learning_value=LearningValue.CURRENT_CLINICAL_CHECK,
        freshness_required=True,
    )
    with pytest.raises(ValueError, match="freshness"):
        blueprint(source_spine=[clinical], freshness_requirements=[])


def test_router_recovers_source_before_teaching():
    decision = LearningRouter().route_next(
        RoutingContext(
            source_spine="costanzo-physiology:ch1",
            source_gap=True,
        )
    )
    assert decision.action == AdaptiveAction.SOURCE_RECOVERY
    assert decision.quality_mode == QualityMode.DEEP


def test_router_verifies_time_sensitive_claim_before_new_teaching():
    decision = LearningRouter().route_next(
        RoutingContext(
            source_spine="katzung:clinical-use",
            current_learning_value=LearningValue.CURRENT_CLINICAL_CHECK,
            freshness_required=True,
            freshness_verified=False,
        )
    )
    assert decision.action == AdaptiveAction.VERIFY_CURRENT_EVIDENCE
    assert decision.quality_mode == QualityMode.CRITICAL


def test_reference_only_item_is_covered_without_becoming_mastery_target():
    decision = LearningRouter().route_next(
        RoutingContext(
            source_spine="moore:variant-detail",
            current_learning_value=LearningValue.REFERENCE_ONLY,
        )
    )
    assert decision.action == AdaptiveAction.REFERENCE_COVERAGE


def test_bootstrap_resumes_unfinished_session_before_new_one():
    paused = session().start().pause(
        SessionCheckpoint(
            concept_id="nernst",
            question_id="q7",
            hint_level=2,
            source_ref=source_ref(),
        )
    )
    plan = build_bootstrap_plan(
        command=Hoc90Command.START,
        resumable_session=paused,
        active_blueprint=blueprint(),
        approved_curriculum_position="foundation/membrane",
    )
    assert plan.mode == BootstrapMode.RESUME
    assert plan.resume_question_id == "q7"
    assert plan.resume_hint_level == 2


def test_new_session_requires_approved_curriculum():
    plan = build_bootstrap_plan(
        command=Hoc90Command.START,
        resumable_session=None,
        active_blueprint=blueprint(),
        approved_curriculum_position=None,
    )
    assert plan.mode == BootstrapMode.NEEDS_CURRICULUM


def test_blueprint_and_structured_source_spine_persist():
    store = SupabaseLearningStateStore(FakeClient())
    plan = blueprint()
    store.save_blueprint(plan)

    loaded = store.get_active_blueprint()
    assert loaded is not None
    assert loaded.primary_source.logical_source_id == "costanzo-physiology"

    saved_session = session().start()
    store.save_session(saved_session)
    raw = store.client.tables["mls_learning_sessions"][0]
    assert raw["source_spine"][0]["logical_source_id"] == "costanzo-physiology"


def test_integrated_blueprint_requires_multiple_logical_books():
    with pytest.raises(ValueError, match="at least two logical books"):
        blueprint(
            study_mode=StudyMode.INTEGRATED_ON_DEMAND,
            integration_goal="Connect anatomy to physiology and rehabilitation.",
        )


def test_integrated_blueprint_preserves_primary_source_return_target():
    support = source_ref(
        logical_source_id="junqueira-basic-histology",
        source_map_node_id="ch10-muscle-tissue",
        source_id="junqueira--physical",
        source_anchor={"page_start": 210},
        learning_value=LearningValue.SUPPORTING,
    )
    plan = blueprint(
        study_mode=StudyMode.INTEGRATED_ON_DEMAND,
        integration_goal="Explain muscle from tissue structure to function.",
        source_spine=[source_ref(), support],
    )
    assert plan.primary_source.logical_source_id == "costanzo-physiology"
    assert plan.return_to_source_spine == (
        "costanzo-physiology:ch1-membrane-potential"
    )


def test_router_opens_integration_only_when_learner_requests_it():
    decision = LearningRouter().route_next(
        RoutingContext(
            source_spine="moore:hip-joint",
            learner_requested_integration=True,
        )
    )
    assert decision.action == AdaptiveAction.CROSS_BOOK_EXPANSION
    assert decision.quality_mode == QualityMode.DEEP
    assert decision.return_to_source_spine == "moore:hip-joint"


def test_router_keeps_sequential_chapter_mode_by_default():
    decision = LearningRouter().route_next(
        RoutingContext(source_spine="moore:hip-joint")
    )
    assert decision.action == AdaptiveAction.CONTINUE_SOURCE_SPINE


def test_source_recovery_still_precedes_requested_integration():
    decision = LearningRouter().route_next(
        RoutingContext(
            source_spine="moore:hip-joint",
            learner_requested_integration=True,
            source_gap=True,
        )
    )
    assert decision.action == AdaptiveAction.SOURCE_RECOVERY
