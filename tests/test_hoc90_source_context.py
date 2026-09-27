import pytest

from medical_learning_system.hoc90.session import SourceSpineRef
from medical_learning_system.hoc90.source_context import (
    SourceContextUnavailable,
    SupabaseHoc90SourceContextResolver,
)


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters = []
        self.ids = None
        self.orders = []

    def select(self, _fields):
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def in_(self, field, values):
        assert field == "evidence_id"
        self.ids = set(values)
        return self

    def order(self, field, desc=False):
        self.orders.append((field, desc))
        return self

    def execute(self):
        rows = [
            row for row in self.rows
            if all(row.get(field) == value for field, value in self.filters)
        ]
        if self.ids is not None:
            rows = [row for row in rows if row.get("evidence_id") in self.ids]
        for field, desc in reversed(self.orders):
            rows.sort(key=lambda row: row.get(field), reverse=desc)
        return Response(rows)


class Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Query(self.tables.get(name, []))


def _ref():
    return SourceSpineRef(
        logical_source_id="guyton-hall-physiology",
        source_map_node_id="ch2-sec1",
        source_id="guyton-physical",
    )


def test_resolver_prefers_promoted_source_map_links():
    client = Client(
        {
            "mls_source_map_evidence_links": [
                {
                    "logical_source_id": "guyton-hall-physiology",
                    "evidence_id": "new",
                    "source_id": "guyton-physical",
                    "node_id": "ch2-sec1",
                    "confidence": 1.0,
                }
            ],
            "mls_evidence_structure_links": [
                {
                    "evidence_id": "legacy",
                    "source_id": "guyton-physical",
                    "node_id": "ch2-sec1",
                    "confidence": 1.0,
                }
            ],
            "mls_evidence_blocks": [
                {
                    "evidence_id": "new",
                    "source_id": "guyton-physical",
                    "page_index": 10,
                    "block_index": 1,
                    "content_type": "text",
                    "text": "promoted map evidence",
                },
                {
                    "evidence_id": "legacy",
                    "source_id": "guyton-physical",
                    "page_index": 9,
                    "block_index": 1,
                    "content_type": "text",
                    "text": "legacy evidence",
                },
            ],
        }
    )
    result = SupabaseHoc90SourceContextResolver(client).resolve(_ref())
    assert result.passages == ["promoted map evidence"]
    assert result.evidence_ids == ["new"]


def test_resolver_uses_exact_legacy_links_when_new_links_absent():
    client = Client(
        {
            "mls_source_map_evidence_links": [],
            "mls_evidence_structure_links": [
                {
                    "evidence_id": "e2",
                    "source_id": "guyton-physical",
                    "node_id": "ch2-sec1",
                    "confidence": 0.9,
                },
                {
                    "evidence_id": "e1",
                    "source_id": "guyton-physical",
                    "node_id": "ch2-sec1",
                    "confidence": 1.0,
                },
            ],
            "mls_evidence_blocks": [
                {
                    "evidence_id": "e2",
                    "source_id": "guyton-physical",
                    "page_index": 11,
                    "block_index": 2,
                    "content_type": "text",
                    "text": "second",
                },
                {
                    "evidence_id": "e1",
                    "source_id": "guyton-physical",
                    "page_index": 10,
                    "block_index": 1,
                    "content_type": "text",
                    "text": "first",
                },
            ],
        }
    )
    result = SupabaseHoc90SourceContextResolver(client).resolve(_ref())
    assert result.passages == ["first", "second"]
    assert result.page_start == 10
    assert result.page_end == 11


def test_resolver_falls_back_only_to_exact_legacy_scalar_alignment():
    client = Client(
        {
            "mls_source_map_evidence_links": [],
            "mls_evidence_structure_links": [],
            "mls_evidence_blocks": [
                {
                    "evidence_id": "e1",
                    "source_id": "guyton-physical",
                    "structure_node_id": "ch2-sec1",
                    "page_index": 10,
                    "block_index": 1,
                    "content_type": "text",
                    "text": "legacy exact alignment",
                },
                {
                    "evidence_id": "other",
                    "source_id": "guyton-physical",
                    "structure_node_id": "ch2-sec2",
                    "page_index": 11,
                    "block_index": 1,
                    "content_type": "text",
                    "text": "must not leak",
                },
            ],
        }
    )
    result = SupabaseHoc90SourceContextResolver(client).resolve(_ref())
    assert result.passages == ["legacy exact alignment"]


def test_resolver_fails_closed_when_exact_evidence_is_missing():
    client = Client(
        {
            "mls_source_map_evidence_links": [],
            "mls_evidence_structure_links": [],
            "mls_evidence_blocks": [],
        }
    )
    with pytest.raises(SourceContextUnavailable, match="No exact text evidence"):
        SupabaseHoc90SourceContextResolver(client).resolve(_ref())


def test_resolver_requires_specific_physical_and_map_identity():
    bad = SourceSpineRef(logical_source_id="guyton-hall-physiology")
    with pytest.raises(SourceContextUnavailable, match="source_id"):
        SupabaseHoc90SourceContextResolver(Client({})).resolve(bad)
