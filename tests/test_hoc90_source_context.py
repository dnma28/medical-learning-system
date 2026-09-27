import pytest

from medical_learning_system.hoc90.session import SourceSpineRef
from medical_learning_system.hoc90.source_context import (
    SourceContextErrorCode,
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
        self.limit_count = None

    def select(self, _fields, **_kwargs):
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

    def limit(self, count):
        self.limit_count = count
        return self

    def execute(self):
        rows = [
            row
            for row in self.rows
            if all(row.get(field) == value for field, value in self.filters)
        ]
        if self.ids is not None:
            rows = [row for row in rows if row.get("evidence_id") in self.ids]
        for field, desc in reversed(self.orders):
            rows.sort(key=lambda row: row.get(field), reverse=desc)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return Response(rows)


class Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Query(self.tables.get(name, []))


def _ref():
    return SourceSpineRef(
        logical_source_id="costanzo-physiology",
        source_map_node_id="ch1-sec1",
        source_id="costanzo-physical",
    )


def _base_tables():
    return {
        "mls_logical_sources": [
            {
                "logical_source_id": "costanzo-physiology",
                "promoted_staging_version": 3,
                "source_map_version": 1,
            }
        ],
        "mls_source_map_nodes": [
            {
                "logical_source_id": "costanzo-physiology",
                "node_id": "ch1-sec1",
                "source_id": "costanzo-physical",
            }
        ],
        "mls_source_map_evidence_status": [],
        "mls_source_map_evidence_links": [],
        "mls_evidence_structure_links": [],
        "mls_evidence_blocks": [],
    }


def test_ready_book_uses_promoted_links_and_ignores_legacy():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 3,
            "state": "ready",
        }
    ]
    tables["mls_source_map_evidence_links"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 3,
            "source_id": "costanzo-physical",
            "node_id": "ch1-sec1",
            "evidence_id": "new",
            "confidence": 1.0,
            "status": "promoted",
        }
    ]
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "ch1-sec1",
            "evidence_id": "legacy",
            "confidence": 1.0,
        }
    ]
    tables["mls_evidence_blocks"] = [
        {
            "evidence_id": "new",
            "source_id": "costanzo-physical",
            "page_index": 10,
            "block_index": 1,
            "content_type": "text",
            "text": "promoted map evidence",
        },
        {
            "evidence_id": "legacy",
            "source_id": "costanzo-physical",
            "page_index": 9,
            "block_index": 1,
            "content_type": "text",
            "text": "legacy evidence",
        },
    ]

    result = SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert result.passages == ["promoted map evidence"]
    assert result.evidence_ids == ["new"]


def test_ready_book_never_silently_falls_back_to_legacy():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 3,
            "state": "ready",
        }
    ]
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "ch1-sec1",
            "evidence_id": "legacy",
            "confidence": 1.0,
        }
    ]
    tables["mls_evidence_blocks"] = [
        {
            "evidence_id": "legacy",
            "source_id": "costanzo-physical",
            "page_index": 9,
            "block_index": 1,
            "content_type": "text",
            "text": "must not be used",
        }
    ]

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.SOURCE_GAP


def test_review_required_link_surfaces_review_required():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 3,
            "state": "ready",
        }
    ]
    tables["mls_source_map_evidence_links"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 3,
            "source_id": "costanzo-physical",
            "node_id": "ch1-sec1",
            "evidence_id": "candidate",
            "confidence": 0.8,
            "status": "review_required",
        }
    ]

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.REVIEW_REQUIRED


def test_previous_ready_version_disables_legacy_after_new_promotion():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 2,
            "state": "ready",
        },
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 3,
            "state": "review_required",
        },
    ]
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "ch1-sec1",
            "evidence_id": "legacy",
            "confidence": 1.0,
        }
    ]

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.SOURCE_GAP
    assert "Legacy fallback is disabled" in str(raised.value)


def test_unmigrated_book_can_use_exact_legacy_links():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 3,
            "state": "review_required",
        }
    ]
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "ch1-sec1",
            "evidence_id": "e2",
            "confidence": 0.9,
        },
        {
            "source_id": "costanzo-physical",
            "node_id": "ch1-sec1",
            "evidence_id": "e1",
            "confidence": 1.0,
        },
    ]
    tables["mls_evidence_blocks"] = [
        {
            "evidence_id": "e2",
            "source_id": "costanzo-physical",
            "page_index": 11,
            "block_index": 2,
            "content_type": "text",
            "text": "second",
        },
        {
            "evidence_id": "e1",
            "source_id": "costanzo-physical",
            "page_index": 10,
            "block_index": 1,
            "content_type": "text",
            "text": "first",
        },
    ]

    result = SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert result.passages == ["first", "second"]


def test_node_physical_source_affinity_is_checked_before_resolution():
    tables = _base_tables()
    tables["mls_source_map_nodes"][0]["source_id"] = "other-physical"

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.INVALID_REFERENCE


def test_resolver_requires_specific_physical_and_map_identity():
    bad = SourceSpineRef(logical_source_id="costanzo-physiology")
    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client({})).resolve(bad)

    assert raised.value.code == SourceContextErrorCode.INVALID_REFERENCE
