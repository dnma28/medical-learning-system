import asyncio

import pytest

from medical_learning_system.deeptutor_adapter import DeepTutorHoc90Adapter
from medical_learning_system.deeptutor_runtime import (
    DeepTutorReadingInput,
    DeepTutorRuntimeExecutor,
)
from medical_learning_system.hoc90.deeptutor_bridge import (
    DeepTutorSubmission,
    Hoc90DeepTutorBridge,
)
from medical_learning_system.hoc90.session import (
    Hoc90Session,
    SessionStage,
    SourceSpineRef,
)
from medical_learning_system.learning.router import (
    AdaptiveAction,
    QualityMode,
    RoutingDecision,
)


class FakeStore:
    def __init__(self, session):
        self.session = session
        self.events = []

    def get_session(self, session_id):
        return self.session if self.session.session_id == session_id else None

    def save_session(self, session):
        self.session = session
        return session

    def commit_deeptutor_submission(
        self,
        *,
        event,
        resumed_session,
        interaction_id,
    ):
        existing = next(
            (
                item
                for item in self.events
                if item.metadata.get("deeptutor_interaction_id") == interaction_id
            ),
            None,
        )
        if existing is not None:
            assert existing.event_id == event.event_id
            return existing
        self.events.append(event)
        self.session = resumed_session
        return event


def _session():
    return Hoc90Session(
        session_id="session-1",
        topic="Membrane transport",
        target_outcome="Explain one source-grounded mechanism",
        source_spine=[
            SourceSpineRef(
                logical_source_id="guyton-hall-physiology",
                source_map_node_id="chapter-2",
                source_id="guyton-physical",
                source_anchor={"page_start": 20},
            )
        ],
        stages=[
            SessionStage(name="learn", minutes=60, objective="Reason"),
            SessionStage(name="test", minutes=30, objective="Retrieve"),
        ],
    ).start()


def _decision(action=AdaptiveAction.CONTINUE_SOURCE_SPINE):
    return RoutingDecision(
        action=action,
        quality_mode=QualityMode.DEEP,
        reason="test",
        target_ids=["membrane-transport"],
        return_to_source_spine="guyton-hall-physiology:chapter-2",
    )


def test_prepare_pauses_session_and_submit_appends_event_then_resumes():
    async def scenario():
        async def runner(task, reading, source_text):
            assert "verified passage" in source_text
            return {
                "type": "card",
                "title": "Study guidance",
                "message": "Explain the relationship.",
                "payload": {"steps": ["find evidence", "connect ideas", "explain"]},
            }

        store = FakeStore(_session())
        bridge = Hoc90DeepTutorBridge(
            store=store,
            executor=DeepTutorRuntimeExecutor(runner=runner),
        )

        prepared = await bridge.prepare(
            session_id="session-1",
            decision=_decision(),
            source_context=["verified passage"],
            reading=DeepTutorReadingInput(material_id="guyton"),
        )

        assert store.session.status.value == "paused"
        pending = store.session.checkpoint.pending_deeptutor_interaction
        assert pending["interaction_id"] == prepared.interaction.interaction_id

        event = bridge.submit(
            session_id="session-1",
            submission=DeepTutorSubmission(
                interaction_id=prepared.interaction.interaction_id,
                learner_response="The mechanism depends on the verified relationship.",
            ),
        )

        assert len(store.events) == 1
        assert event.metadata["automatic_mastery_credit"] is False
        assert store.session.status.value == "active"
        assert store.session.checkpoint.pending_deeptutor_interaction is None

    asyncio.run(scenario())


def test_submit_uses_stable_event_identity_for_interaction():
    async def scenario():
        async def runner(task, reading, source_text):
            return {
                "type": "card",
                "title": "Study guidance",
                "message": "Explain.",
                "payload": {"steps": ["one"]},
            }

        store = FakeStore(_session())
        bridge = Hoc90DeepTutorBridge(
            store=store,
            executor=DeepTutorRuntimeExecutor(runner=runner),
        )
        prepared = await bridge.prepare(
            session_id="session-1",
            decision=_decision(),
            source_context=["verified passage"],
            reading=DeepTutorReadingInput(material_id="guyton"),
        )
        event = bridge.submit(
            session_id="session-1",
            submission=DeepTutorSubmission(
                interaction_id=prepared.interaction.interaction_id,
                learner_response="answer",
            ),
        )
        expected = Hoc90DeepTutorBridge._stable_submission_event_id(
            "session-1", prepared.interaction.interaction_id
        )
        assert event.event_id == expected
        assert len(store.events) == 1
        assert store.session.status.value == "active"

    asyncio.run(scenario())


def test_prepare_refuses_to_overwrite_pending_interaction():
    async def scenario():
        async def runner(task, reading, source_text):
            return {
                "type": "card",
                "title": "Study guidance",
                "message": "focus",
                "payload": {"steps": ["one", "two", "three"]},
            }

        store = FakeStore(_session())
        bridge = Hoc90DeepTutorBridge(
            store=store,
            executor=DeepTutorRuntimeExecutor(runner=runner),
        )
        await bridge.prepare(
            session_id="session-1",
            decision=_decision(),
            source_context=["verified passage"],
            reading=DeepTutorReadingInput(material_id="guyton"),
        )

        with pytest.raises(RuntimeError, match="pending DeepTutor"):
            await bridge.prepare(
                session_id="session-1",
                decision=_decision(),
                source_context=["verified passage"],
                reading=DeepTutorReadingInput(material_id="guyton"),
            )

    asyncio.run(scenario())


def test_quiz_answer_key_survives_checkpoint_but_is_not_public():
    async def scenario():
        async def runner(task, reading, source_text):
            return {
                "type": "quiz",
                "title": "Reading quiz",
                "message": "Questions use the passage.",
                "payload": {
                    "questions": [
                        {
                            "id": "q_1",
                            "prompt": "Which statement is supported?",
                            "choices": ["A", "B", "C", "D"],
                            "correct_choice_index": 1,
                        }
                    ]
                },
            }

        store = FakeStore(_session())
        bridge = Hoc90DeepTutorBridge(
            store=store,
            executor=DeepTutorRuntimeExecutor(runner=runner),
            adapter=DeepTutorHoc90Adapter(),
        )
        prepared = await bridge.prepare(
            session_id="session-1",
            decision=_decision(),
            source_context=["verified passage"],
            reading=DeepTutorReadingInput(material_id="guyton"),
            quiz=True,
        )

        public_dump = prepared.model_dump(mode="json")
        assert "correct_choice_index" not in str(public_dump)

        pending = store.session.checkpoint.pending_deeptutor_interaction
        assert pending["private_evaluation"]["answer_key"]["q_1"] == 1

        event = bridge.submit(
            session_id="session-1",
            submission=DeepTutorSubmission(
                interaction_id=prepared.interaction.interaction_id,
                question_id="q_1",
                selected_choice_index=1,
            ),
        )
        assert event.outcome == "correct"
        assert event.metadata["evidence_ceiling"] == "M1"

    asyncio.run(scenario())


def test_stale_interaction_id_is_rejected_without_event():
    async def scenario():
        async def runner(task, reading, source_text):
            return {
                "type": "card",
                "title": "Study guidance",
                "message": "focus",
                "payload": {"steps": ["one", "two", "three"]},
            }

        store = FakeStore(_session())
        bridge = Hoc90DeepTutorBridge(
            store=store,
            executor=DeepTutorRuntimeExecutor(runner=runner),
        )
        await bridge.prepare(
            session_id="session-1",
            decision=_decision(),
            source_context=["verified passage"],
            reading=DeepTutorReadingInput(material_id="guyton"),
        )

        with pytest.raises(RuntimeError, match="interaction_id"):
            bridge.submit(
                session_id="session-1",
                submission=DeepTutorSubmission(
                    interaction_id="stale-id",
                    learner_response="answer",
                ),
            )
        assert store.events == []

    asyncio.run(scenario())
