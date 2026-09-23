from medical_learning_system.hoc90 import Hoc90Session, SessionStage


def test_hoc90_duration():
    session = Hoc90Session(
        topic="Membrane potential",
        target_outcome="Explain the mechanism from first principles",
        stages=[
            SessionStage(name="A", minutes=20, objective="Build model"),
            SessionStage(name="B", minutes=30, objective="Work examples"),
            SessionStage(name="C", minutes=25, objective="Recall"),
            SessionStage(name="D", minutes=15, objective="Transfer"),
        ],
    )
    assert session.is_90_minutes()
