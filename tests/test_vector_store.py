import pytest

from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.retrieval.vector_store import (
    EvidenceEmbedding,
    SupabaseRetrievalStore,
)


class Response:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.filters = []
        self.mode = "select"
        self.payload = None
        self.select_fields = "*"
        self.limit_count = None
        self.conflict = ""

    def select(self, fields):
        self.mode = "select"
        self.select_fields = fields
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def upsert(self, payload, on_conflict=""):
        self.mode = "upsert"
        self.payload = payload
        self.conflict = on_conflict
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        if self.mode == "select":
            matched = [
                row for row in rows
                if all(row.get(field) == value for field, value in self.filters)
            ]
            if self.limit_count is not None:
                matched = matched[: self.limit_count]
            if self.select_fields != "*":
                fields = [field.strip() for field in self.select_fields.split(",")]
                matched = [
                    {field: row.get(field) for field in fields} for row in matched
                ]
            return Response([dict(row) for row in matched])

        if self.mode == "upsert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            keys = [key for key in self.conflict.split(",") if key]
            for item in items:
                existing = next(
                    (
                        row for row in rows
                        if keys and all(row.get(key) == item.get(key) for key in keys)
                    ),
                    None,
                )
                if existing is None:
                    rows.append(dict(item))
                else:
                    existing.update(item)
            return Response(items)

        raise AssertionError(self.mode)


class FakeRpc:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.rpc_calls.append((self.name, self.params))
        return Response(self.client.rpc_results.get(self.name, []))


class FakeClient:
    def __init__(self):
        self.tables = {}
        self.rpc_calls = []
        self.rpc_results = {}

    def table(self, name):
        return FakeTable(self, name)

    def rpc(self, name, params):
        return FakeRpc(self, name, params)


def evidence(text="K permeability"):
    return make_evidence_block(
        source_id="costanzo",
        block_index=0,
        page_index=10,
        content_type=EvidenceContentType.TEXT,
        parser="docling",
        text=text,
    )


def test_embedding_dimension_must_match_vector_length():
    with pytest.raises(ValueError, match="embedding length"):
        EvidenceEmbedding(
            evidence_id="ev-1",
            embedding_model="model-a",
            embedding_dim=3,
            embedding=[0.1, 0.2],
            content_sha256="a" * 64,
        )


def test_multiple_models_can_coexist_for_same_evidence():
    client = FakeClient()
    store = SupabaseRetrievalStore(client)

    for model, vector in [
        ("model-a", [0.1, 0.2]),
        ("model-b", [0.3, 0.4, 0.5]),
    ]:
        store.upsert_embedding(
            EvidenceEmbedding(
                evidence_id="ev-1",
                embedding_model=model,
                embedding_dim=len(vector),
                embedding=vector,
                content_sha256="a" * 64,
            )
        )

    rows = client.tables[SupabaseRetrievalStore.EMBEDDINGS]
    assert len(rows) == 2
    assert {row["embedding_model"] for row in rows} == {"model-a", "model-b"}


def test_content_hash_prevents_unnecessary_reembedding():
    client = FakeClient()
    store = SupabaseRetrievalStore(client)
    block = evidence()

    assert store.needs_embedding(block, "model-a") is True

    store.upsert_embedding(
        EvidenceEmbedding(
            evidence_id=block.evidence_id,
            embedding_model="model-a",
            embedding_dim=2,
            embedding=[0.1, 0.2],
            content_sha256=block.content_sha256,
        )
    )
    assert store.needs_embedding(block, "model-a") is False

    changed = evidence("changed content")
    # Same logical retrieval check can only reuse an embedding when the exact
    # persisted evidence ID/hash matches; changed evidence must be embedded.
    assert store.needs_embedding(changed, "model-a") is True


def test_semantic_search_always_names_embedding_model():
    client = FakeClient()
    client.rpc_results["mls_match_evidence"] = [
        {
            "evidence_id": "ev-1",
            "source_id": "costanzo",
            "structure_node_ids": ["chapter-1", "section-1"],
            "page_index": 10,
            "content_type": "text",
            "text": "K permeability",
            "similarity": 0.91,
        }
    ]
    store = SupabaseRetrievalStore(client)

    hits = store.semantic_search(
        query_embedding=[0.1, 0.2],
        embedding_model="model-a",
        source_ids=["costanzo"],
    )

    assert hits[0].score == 0.91
    assert hits[0].structure_node_ids == {"chapter-1", "section-1"}
    name, params = client.rpc_calls[-1]
    assert name == "mls_match_evidence"
    assert params["embedding_model_filter"] == "model-a"
    assert params["source_ids"] == ["costanzo"]


def test_keyword_search_requires_no_embedding():
    client = FakeClient()
    client.rpc_results["mls_keyword_evidence"] = [
        {
            "evidence_id": "ev-2",
            "source_id": "guyton",
            "structure_node_ids": [],
            "page_index": 4,
            "content_type": "text",
            "text": "resting membrane potential",
            "rank": 0.72,
        }
    ]
    store = SupabaseRetrievalStore(client)

    hits = store.keyword_search("resting membrane potential")

    assert hits[0].source_id == "guyton"
    assert hits[0].score == 0.72
    assert client.rpc_calls[-1][0] == "mls_keyword_evidence"
