from pathlib import Path

from medical_learning_system.evidence_alignment import (
    AlignmentMethod,
    EvidenceLinkStore,
    EvidenceStructureLink,
)
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    EvidenceStore,
    make_evidence_block,
)
from medical_learning_system.retrieval.local_retrievers import (
    LocalKeywordRetriever,
    LocalSemanticRetriever,
)


SOURCE = "source-1"


def seed(tmp_path: Path):
    db = tmp_path / "pilot.sqlite3"
    evidence = EvidenceStore(db)
    links = EvidenceLinkStore(db)

    blocks = [
        make_evidence_block(
            source_id=SOURCE,
            block_index=0,
            page_index=0,
            content_type=EvidenceContentType.TEXT,
            parser="test",
            text="resting membrane potential potassium permeability",
        ),
        make_evidence_block(
            source_id=SOURCE,
            block_index=1,
            page_index=1,
            content_type=EvidenceContentType.TEXT,
            parser="test",
            text="skeletal muscle contraction calcium",
        ),
    ]
    evidence.replace_source(SOURCE, blocks)
    links.replace_source(
        SOURCE,
        [
            EvidenceStructureLink(
                evidence_id=blocks[0].evidence_id,
                source_id=SOURCE,
                node_id="resting",
                method=AlignmentMethod.HEADING_SEQUENCE,
                confidence=0.95,
            ),
            EvidenceStructureLink(
                evidence_id=blocks[1].evidence_id,
                source_id=SOURCE,
                node_id="muscle",
                method=AlignmentMethod.HEADING_SEQUENCE,
                confidence=0.95,
            ),
        ],
    )
    return evidence, links, blocks


def test_keyword_retriever_returns_source_grounded_links(tmp_path):
    evidence, links, blocks = seed(tmp_path)
    retriever = LocalKeywordRetriever(evidence, links, SOURCE)

    response = retriever.retrieve("potassium membrane", 2)

    assert response.estimated_cost_usd == 0.0
    assert response.hits[0].evidence_id == blocks[0].evidence_id
    assert response.hits[0].structure_node_ids == {"resting"}


class FakeProvider:
    name = "fake-embedding"
    dimension = 2

    def encode(self, texts):
        mapping = {
            "resting membrane potential potassium permeability": [1.0, 0.0],
            "skeletal muscle contraction calcium": [0.0, 1.0],
            "membrane voltage": [1.0, 0.0],
        }
        return [mapping[text] for text in texts]


def test_semantic_retriever_is_provider_neutral(tmp_path):
    evidence, links, blocks = seed(tmp_path)
    retriever = LocalSemanticRetriever(
        evidence,
        links,
        SOURCE,
        FakeProvider(),
    )

    response = retriever.retrieve("membrane voltage", 1)

    assert response.hits[0].evidence_id == blocks[0].evidence_id
    assert response.hits[0].structure_node_ids == {"resting"}
    assert response.estimated_cost_usd == 0.0
