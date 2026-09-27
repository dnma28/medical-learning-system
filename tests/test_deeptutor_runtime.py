import asyncio

import pytest

from medical_learning_system.deeptutor_adapter import (
    DeepTutorCapability,
    DeepTutorHoc90Adapter,
)
from medical_learning_system.deeptutor_runtime import (
    DeepTutorReadingInput,
    DeepTutorRuntimeExecutor,
)
from medical_learning_system.learning.router import (
    AdaptiveAction,
    QualityMode,
    RoutingDecision,
)


def _decision(action: AdaptiveAction) -> RoutingDecision:
    return RoutingDecision(
        action=action,
        quality_mode=QualityMode.DEEP,
        reason="test",
        target_ids=["concept-1"],
        return_to_source_spine="Guyton ch2",
    )


def test_guided_learning_executes_with_injected_runner():
    async def scenario():
        async def runner(task, reading, source_text):
            assert task.capability == DeepTutorCapability.GUIDED_LEARNING
            assert reading.material_id == "guyton"
            assert "verified passage" in source_text
            return {
                "type": "card",
                "title": "Study guidance",
                "message": "focus",
                "payload": {"steps": ["one", "two", "three"]},
            }

        task = DeepTutorHoc90Adapter().build_task(
            _decision(AdaptiveAction.CONTINUE_SOURCE_SPINE),
            source_context=["verified passage"],
        )
        result = await DeepTutorRuntimeExecutor(runner=runner).execute(
            task,
            reading=DeepTutorReadingInput(material_id="guyton", locator=2),
        )
        assert result.result_type == "card"
        assert result.payload["steps"] == ["one", "two", "three"]
        assert result.authoritative is False
        assert len(result.source_sha256) == 64

    asyncio.run(scenario())


def test_quiz_answer_key_is_private_and_event_is_m1_only():
    async def scenario():
        async def runner(task, reading, source_text):
            return {
                "type": "quiz",
                "title": "Reading quiz",
                "message": "Questions use the current passage.",
                "payload": {
                    "questions": [
                        {
                            "id": "q_1",
                            "prompt": "Which statement is supported?",
                            "choices": ["A", "B", "C", "D"],
                            "correct_choice_index": 2,
                        }
                    ]
                },
            }

        adapter = DeepTutorHoc90Adapter()
        task = adapter.build_reading_quiz(
            _decision(AdaptiveAction.CONTINUE_SOURCE_SPINE),
            source_context=["verified passage"],
        )
        result = await DeepTutorRuntimeExecutor(runner=runner).execute(
            task,
            reading=DeepTutorReadingInput(material_id="guyton"),
        )

        dumped = result.model_dump(mode="json")
        assert "private_evaluation" not in dumped
        assert "correct_choice_index" not in str(dumped)
        assert result.private_evaluation["answer_key"]["q_1"] == 2

        event = DeepTutorRuntimeExecutor.build_quiz_answer_event_candidate(
            session_id="session-1",
            task=task,
            execution=result,
            question_id="q_1",
            selected_choice_index=2,
        )
        assert event.outcome == "correct"
        assert event.metadata["evidence_kind"] == "recognition"
        assert event.metadata["evidence_ceiling"] == "M1"
        assert event.metadata["automatic_mastery_credit"] is False

    asyncio.run(scenario())


def test_mls_native_action_cannot_be_executed_by_deeptutor():
    async def scenario():
        called = False

        async def runner(task, reading, source_text):
            nonlocal called
            called = True
            return {}

        task = DeepTutorHoc90Adapter().build_task(
            _decision(AdaptiveAction.TRANSFER),
            source_context=["verified passage"],
        )
        with pytest.raises(ValueError, match="MLS-native"):
            await DeepTutorRuntimeExecutor(runner=runner).execute(
                task,
                reading=DeepTutorReadingInput(material_id="guyton"),
            )
        assert called is False

    asyncio.run(scenario())


def test_guided_learning_rejects_unbounded_selection():
    async def scenario():
        async def runner(task, reading, source_text):
            return {}

        task = DeepTutorHoc90Adapter().build_task(
            _decision(AdaptiveAction.CONTINUE_SOURCE_SPINE),
            source_context=["x" * 10_001],
        )
        with pytest.raises(ValueError, match="10,000"):
            await DeepTutorRuntimeExecutor(runner=runner).execute(
                task,
                reading=DeepTutorReadingInput(material_id="guyton"),
            )

    asyncio.run(scenario())
