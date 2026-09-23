from medical_learning_system.hoc90.session import (
    Hoc90Session,
    LearningEvent,
    LearningEventType,
    SessionCheckpoint,
    SessionStage,
    SessionStatus,
)
from medical_learning_system.learning.router import (
    AdaptiveAction,
    LearningRouter,
    QualityMode,
    RoutingContext,
)
from medical_learning_system.student.models import (
    ConceptMastery,
    ErrorStatus,
    ErrorType,
    LearnerError,
    MasteryLevel,
)
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
        self.filters = []
        self.in_filters = []
        self.mode = "select"
        self.payload = None
        self.limit_count = None
        self.order_field = None
        self.order_desc = False
        self.conflict = []

    def select(self, _fields):
        self.mode = "select"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, set(values)))
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def insert(self, payload):
        self.mode = "insert"
        self.payload = payload
        return self

    def upsert(self, payload, on_conflict=""):
        self.mode = "upsert"
        self.payload = payload
        self.conflict = [part for part in on_conflict.split(",") if part]
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])

        if self.mode == "insert":
            if any(row.get("event_id") == self.payload.get("event_id") for row in rows):
                raise ValueError("duplicate")
            rows.append(dict(self.payload))
            return Response([dict(self.payload)])

        if self.mode == "upsert":
            existing = next(
                (
                    row
                    for row in rows
                    if self.conflict
                    and all(row.get(key) == self.payload.get(key) for key in self.conflict)
                ),
                None,
            )
            if existing is None:
                rows.append(dict(self.payload))
                stored = rows[-1]
            else:
                existing.update(self.payload)
                stored = existing
            return Response([dict(stored)])

        matched = [
            row
            for row in rows
            if all(row.get(field) == value for field, value in self.filters)
            and all(row.get(field) in values for field, values in self.in_filters)
        ]
        if self.order_field:
            matched.sort(
                key=lambda row: row.get(self.order_field),
                reverse=self.order_desc,
            )
        if self.limit_count is not None:
            matched = matched[: self.limit_count]
        return Response([dict(row) for row in matched])


class FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return FakeQuery(self, name)


def make_session():
    return Hoc90Session(
        topic="Điện thế màng",
        target_outcome="Giải thích từ gradient điện hóa đến điện thế nghỉ",
        curriculum_position="foundation/membrane",
        source_spine=["costanzo-6e/ch1"],
        stages=[
            SessionStage(name="retrieval", minutes=10, objective="Recall"),
            SessionStage(name="reasoning", minutes=55, objective="Mechanism"),
            SessionStage(name="transfer", minutes=25, objective="Apply"),
        ],
    )


def test_hoc90_can_pause_and_resume_from_checkpoint():
    session = make_session().start()
    checkpoint = SessionCheckpoint(
        concept_id="nernst-equation",
        question_id="q7",
        hint_level=1,
        toc_position="costanzo-6e/ch1/equilibrium-potential",
        current_branch="logarithm-prerequisite",
        return_to_source="costanzo-6e/ch1/equilibrium-potential",
    )

    paused = session.pause(checkpoint)
    assert paused.status == SessionStatus.PAUSED
    assert paused.checkpoint.question_id == "q7"

    resumed = paused.resume()
    assert resumed.status == SessionStatus.ACTIVE
    assert resumed.checkpoint.question_id == "q7"


def test_router_prioritizes_retrieval_then_required_prerequisite():
    router = LearningRouter()
    first = router.route_next(
        RoutingContext(
            session_start=True,
            source_spine="costanzo-6e/ch1",
            due_retrieval_concept_ids=["electrochemical-gradient"],
            weak_required_prerequisite_ids=["logarithm"],
        )
    )
    assert first.action == AdaptiveAction.START_RETRIEVAL

    next_step = router.route_next(
        RoutingContext(
            session_start=False,
            source_spine="costanzo-6e/ch1",
            weak_required_prerequisite_ids=["logarithm"],
        )
    )
    assert next_step.action == AdaptiveAction.PREREQUISITE_REPAIR
    assert next_step.return_to_source_spine == "costanzo-6e/ch1"


def test_router_uses_critical_mode_for_time_sensitive_clinical_claims():
    decision = LearningRouter().route_next(
        RoutingContext(
            source_spine="katzung/chapter",
            current_claim_is_time_sensitive_clinical=True,
        )
    )
    assert decision.quality_mode == QualityMode.CRITICAL


def test_learning_state_is_written_incrementally_and_resumable():
    client = FakeClient()
    store = SupabaseLearningStateStore(client)

    session = make_session().start()
    store.save_session(session)

    event = LearningEvent(
        session_id=session.session_id,
        event_type=LearningEventType.SOCRATIC_RESPONSE,
        concept_id="electrochemical-gradient",
        question_id="q1",
        outcome="partial",
        answer_summary="Phân biệt được gradient nồng độ nhưng thiếu lực điện.",
        hint_level=1,
    )
    store.append_event(event)

    mastery = ConceptMastery(
        concept_id="electrochemical-gradient",
        mastery_level=MasteryLevel.M2,
        historical_peak_mastery=MasteryLevel.M2,
        current_strength=0.45,
        retrieval_successes=1,
        evidence_for_mastery=[event.event_id],
    )
    store.upsert_mastery(mastery)

    error = LearnerError(
        id="err-electrochemical-1",
        concept_id="electrochemical-gradient",
        statement="Chỉ xét chênh lệch nồng độ.",
        error_type=ErrorType.MISSING_CONDITION,
        status=ErrorStatus.RETEST_REQUIRED,
    )
    store.upsert_error(error)

    paused = session.pause(
        SessionCheckpoint(
            concept_id="electrochemical-gradient",
            question_id="q2",
            hint_level=0,
            toc_position="costanzo-6e/ch1",
        )
    )
    store.save_session(paused)

    loaded = store.load_resumable_session()
    assert loaded is not None
    assert loaded.status == SessionStatus.PAUSED
    assert loaded.checkpoint.question_id == "q2"

    stored_mastery = store.get_mastery("electrochemical-gradient")
    assert stored_mastery.mastery_level == MasteryLevel.M2
    assert stored_mastery.current_strength == 0.45

    open_errors = store.list_open_errors(concept_id="electrochemical-gradient")
    assert [item.id for item in open_errors] == ["err-electrochemical-1"]


def test_learning_events_are_append_only():
    store = SupabaseLearningStateStore(FakeClient())
    session = make_session().start()
    store.save_session(session)

    event = LearningEvent(
        event_id="event-1",
        session_id=session.session_id,
        event_type=LearningEventType.RETRIEVAL,
    )
    store.append_event(event)

    try:
        store.append_event(event)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate event IDs must not overwrite history")
