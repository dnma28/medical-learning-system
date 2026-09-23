from medical_learning_system.knowledge_graph import (
    Evidence,
    GraphEdge,
    SourceLocator,
    validate_for_promotion,
)


def test_candidate_without_evidence_cannot_promote():
    edge = GraphEdge(id="e1", source="ATP", relation="powers", target="pump")
    decision = validate_for_promotion(edge)
    assert not decision.allowed
    assert "missing_evidence" in decision.reasons


def test_sourced_candidate_can_pass_structural_gate():
    edge = GraphEdge(
        id="e2",
        source="ATP",
        relation="powers",
        target="pump",
        evidence=[
            Evidence(
                locator=SourceLocator(
                    source_id="book-1", title="Example", page=10
                ),
                claim_text="ATP supplies energy for the transport process.",
            )
        ],
    )
    assert validate_for_promotion(edge).allowed
