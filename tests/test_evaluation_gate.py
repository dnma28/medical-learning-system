import pytest

from medical_learning_system.coverage import StructureKind, StructureNode
from medical_learning_system.evidence_alignment import (
    AlignmentMethod,
    EvidenceLinkStore,
    EvidenceStructureLink,
)
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.retrieval.benchmark_gold import (
    SourceGroundedBenchmarkItem,
    SourceHeadingAnchor,
)
from medical_learning_system.retrieval.evaluation_gate import (
    EvaluationGateError,
    GroundedEvidence,
    KeywordBaselineRetriever,
    SemanticCorpusRetriever,
    alignment_coverage,
    build_grounded_corpus,
    evaluate_retrievers,
    resolve_gold_strict,
)


SOURCE = "book-physical"
LOGICAL = "book-logical"


def block(index, text):
    return make_evidence_block(
        source_id=SOURCE,
        block_index=index,
        page_index=index,
        content_type=EvidenceContentType.TEXT,
        parser="test",
        text=text,
    )


def link(block_, node, method=AlignmentMethod.HEADING_SEQUENCE, confidence=0.95):
    return EvidenceStructureLink(
        evidence_id=block_.evidence_id,
        source_id=SOURCE,
        node_id=node,
        method=method,
        confidence=confidence,
    )


def nodes():
    return [
        StructureNode(
            source_id=SOURCE,
            node_id="book",
            kind=StructureKind.BOOK,
            title="Book",
            depth=0,
            order_index=0,
        ),
        StructureNode(
            source_id=SOURCE,
            node_id="chapter",
            parent_id="book",
            kind=StructureKind.CHAPTER,
            title="Cellular Physiology",
            depth=1,
            order_index=1,
            page_start=1,
            page_end=20,
        ),
        StructureNode(
            source_id=SOURCE,
            node_id="membrane",
            parent_id="chapter",
            kind=StructureKind.SECTION,
            title="Resting Membrane Potential",
            depth=2,
            order_index=2,
            page_start=3,
            page_end=5,
        ),
    ]


def gold_item():
    return SourceGroundedBenchmarkItem(
        query_id="q1",
        query_text="Vì sao kali ảnh hưởng điện thế nghỉ?",
        language="vi",
        anchors=[
            SourceHeadingAnchor(
                logical_source_id=LOGICAL,
                chapter_title="Cellular Physiology",
                heading_title="Resting Membrane Potential",
            )
        ],
    )


def test_grounded_corpus_excludes_unlinked_text(tmp_path):
    linked = block(0, "potassium membrane potential")
    unlinked = block(1, "unrelated")
    store = EvidenceLinkStore(tmp_path / "pilot.sqlite3")
    store.replace_source(SOURCE, [link(linked, "membrane")])

    corpus = build_grounded_corpus([linked, unlinked], store)

    assert [item.evidence_id for item in corpus] == [linked.evidence_id]


def test_gold_resolution_fails_when_target_has_no_grounded_evidence(tmp_path):
    store = EvidenceLinkStore(tmp_path / "pilot.sqlite3")

    with pytest.raises(EvaluationGateError, match="no grounded evidence"):
        resolve_gold_strict(
            [gold_item()],
            logical_source_id=LOGICAL,
            physical_source_id=SOURCE,
            nodes=nodes(),
            link_store=store,
        )


def test_alignment_coverage_reports_candidate_only_blocks(tmp_path):
    exact = block(0, "heading")
    candidate = block(1, "body")
    store = EvidenceLinkStore(tmp_path / "pilot.sqlite3")
    store.replace_source(
        SOURCE,
        [
            link(exact, "membrane", AlignmentMethod.EXACT_HEADING, 1.0),
            link(
                candidate,
                "membrane",
                AlignmentMethod.PAGE_RANGE_CANDIDATE,
                0.5,
            ),
        ],
    )

    result = alignment_coverage([exact, candidate], store)

    assert result.grounded_fraction == 1.0
    assert result.exact_evidence == 1
    assert result.candidate_only_evidence == 1


def test_keyword_evaluation_uses_same_resolved_gold(tmp_path):
    membrane = block(0, "potassium membrane resting potential")
    other = block(1, "smooth muscle calcium")
    store = EvidenceLinkStore(tmp_path / "pilot.sqlite3")
    store.replace_source(
        SOURCE,
        [
            link(membrane, "membrane"),
            link(other, "chapter"),
        ],
    )
    queries = resolve_gold_strict(
        [gold_item()],
        logical_source_id=LOGICAL,
        physical_source_id=SOURCE,
        nodes=nodes(),
        link_store=store,
    )
    queries[0] = queries[0].model_copy(
        update={"query_text": "potassium membrane"}
    )
    corpus = build_grounded_corpus([membrane, other], store)

    report, runs = evaluate_retrievers(
        source_id=SOURCE,
        logical_source_id=LOGICAL,
        queries=queries,
        evidence=[membrane, other],
        link_store=store,
        retrievers=[KeywordBaselineRetriever(corpus)],
        k=2,
    )

    assert report.queries == 1
    assert report.languages == {"vi": 1}
    assert len(runs["keyword-token-overlap"]) == 1
    assert report.summaries[0].structure_recall_at_k == 1.0


class FakeEmbeddingProvider:
    name = "fake-medical"
    dimension = 2

    def encode(self, texts):
        vectors = []
        for text in texts:
            lowered = text.casefold()
            if "potassium" in lowered or "kali" in lowered:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


def test_semantic_retriever_is_provider_neutral(tmp_path):
    membrane = block(0, "potassium membrane resting potential")
    other = block(1, "smooth muscle calcium")
    store = EvidenceLinkStore(tmp_path / "pilot.sqlite3")
    store.replace_source(
        SOURCE,
        [
            link(membrane, "membrane"),
            link(other, "chapter"),
        ],
    )
    corpus = build_grounded_corpus([membrane, other], store)
    retriever = SemanticCorpusRetriever(corpus, FakeEmbeddingProvider())

    response = retriever.retrieve("kali điện thế nghỉ", 1)

    assert response.hits[0].evidence_id == membrane.evidence_id
    assert response.hits[0].structure_node_ids == {"membrane"}


def test_keyword_no_overlap_returns_no_hits():
    corpus = [
        GroundedEvidence(
            evidence_id="ev-1",
            source_id=SOURCE,
            text="resting membrane potential potassium permeability",
            structure_node_ids={"membrane"},
        )
    ]
    response = KeywordBaselineRetriever(corpus).retrieve(
        "nước nội bào ngoại bào",
        10,
    )
    assert response.hits == []


def test_evaluation_report_counts_no_hit_queries(tmp_path):
    membrane = block(0, "potassium membrane resting potential")
    store = EvidenceLinkStore(tmp_path / "pilot.sqlite3")
    store.replace_source(SOURCE, [link(membrane, "membrane")])
    queries = resolve_gold_strict(
        [gold_item()],
        logical_source_id=LOGICAL,
        physical_source_id=SOURCE,
        nodes=nodes(),
        link_store=store,
    )
    corpus = build_grounded_corpus([membrane], store)

    report, _ = evaluate_retrievers(
        source_id=SOURCE,
        logical_source_id=LOGICAL,
        queries=queries,
        evidence=[membrane],
        link_store=store,
        retrievers=[KeywordBaselineRetriever(corpus)],
        k=10,
    )

    assert report.no_hit_queries == {"keyword-token-overlap": 1}
