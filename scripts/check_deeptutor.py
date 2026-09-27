"""Verify the upstream DeepTutor APIs used by MLS without calling an LLM."""

from deeptutor.reading.extensions import ReadingContext
from deeptutor.reading.quiz import ReadingQuizExtension
from deeptutor.reading.study_guidance import StudyGuidanceExtension


def main() -> None:
    guidance = StudyGuidanceExtension()
    quiz = ReadingQuizExtension()

    assert guidance.manifest.id == "guided_learning"
    assert any(action.id == "guide" for action in guidance.manifest.actions)
    assert quiz.manifest.id == "quiz"
    assert any(action.id == "start" for action in quiz.manifest.actions)

    context = ReadingContext(
        material_id="smoke",
        locator=1,
        source_anchor="chapter=1",
        locale="vi",
        selection="Verified source selection.",
        visible_text="Verified source selection.",
    )
    assert context.material_id == "smoke"
    print("DeepTutor v1.6.11 reading-extension contract OK")


if __name__ == "__main__":
    main()
