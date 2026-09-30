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
        return Response([dict(row) for row in rows])


class Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Query(self.tables.get(name, []))


def _ref():
    return SourceSpineRef(
        logical_source_id="costanzo-physiology",
        source_map_node_id="outline:0007",
        source_id="costanzo-physical",
    )


def _base_tables():
    return {
        "mls_logical_sources": [
            {
                "logical_source_id": "costanzo-physiology",
                "promoted_staging_version": 4,
                "source_map_version": 1,
            }
        ],
        "mls_source_map_nodes": [
            {
                "logical_source_id": "costanzo-physiology",
                "node_id": "outline:0007",
                "source_id": "costanzo-physical",
            }
        ],
        "mls_source_map_evidence_status": [],
        "mls_source_map_evidence_links": [],
        "mls_evidence_structure_links": [],
        "mls_evidence_blocks": [],
    }


def test_partial_migration_uses_current_promoted_links_and_ignores_legacy():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 4,
            "state": "partial",
            "legacy_fallback_disabled": True,
        }
    ]
    tables["mls_source_map_evidence_links"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 4,
            "source_id": "costanzo-physical",
            "node_id": "outline:0007",
            "evidence_id": "new",
            "confidence": 0.95,
            "status": "promoted",
        }
    ]
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "outline:0007",
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
            "text": "promoted evidence",
        },
        {
            "evidence_id": "legacy",
            "source_id": "costanzo-physical",
            "page_index": 9,
            "block_index": 1,
            "content_type": "text",
            "text": "legacy must not leak",
        },
    ]

    result = SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert result.passages == ["promoted evidence"]
    assert result.evidence_ids == ["new"]


def test_partial_migration_missing_node_link_never_silently_falls_back():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 4,
            "state": "partial",
            "legacy_fallback_disabled": True,
        }
    ]
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "outline:0007",
            "evidence_id": "legacy",
            "confidence": 1.0,
        }
    ]

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.SOURCE_GAP


def test_new_promotion_after_migration_disables_legacy_until_recompiled():
    tables = _base_tables()
    tables["mls_logical_sources"][0]["promoted_staging_version"] = 5
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 4,
            "state": "stale",
            "legacy_fallback_disabled": True,
        }
    ]
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "outline:0007",
            "evidence_id": "legacy",
            "confidence": 1.0,
        }
    ]

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.SOURCE_GAP
    assert "Legacy fallback is disabled" in str(raised.value)


def test_review_required_migration_surfaces_review_required():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 4,
            "state": "review_required",
            "legacy_fallback_disabled": True,
        }
    ]

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.REVIEW_REQUIRED


def test_unmigrated_unpromoted_book_retains_exact_legacy_adapter():
    tables = _base_tables()
    tables["mls_logical_sources"][0]["promoted_staging_version"] = None
    tables["mls_logical_sources"][0]["source_map_version"] = 0
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "outline:0007",
            "evidence_id": "e2",
            "confidence": 0.9,
        },
        {
            "source_id": "costanzo-physical",
            "node_id": "outline:0007",
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


def test_promoted_book_without_versioned_evidence_never_uses_legacy():
    tables = _base_tables()
    tables["mls_evidence_structure_links"] = [
        {
            "source_id": "costanzo-physical",
            "node_id": "outline:0007",
            "evidence_id": "legacy",
            "confidence": 1.0,
        }
    ]
    tables["mls_evidence_blocks"] = [
        {
            "evidence_id": "legacy",
            "source_id": "costanzo-physical",
            "page_index": 10,
            "block_index": 1,
            "content_type": "text",
            "text": "must not be used for a promoted book",
        }
    ]

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.SOURCE_GAP
    assert "promoted Source Map" in str(raised.value)
    assert "Legacy fallback is disabled" in str(raised.value)


def test_migrated_node_physical_source_affinity_is_checked():
    tables = _base_tables()
    tables["mls_source_map_evidence_status"] = [
        {
            "logical_source_id": "costanzo-physiology",
            "staging_version": 4,
            "state": "partial",
            "legacy_fallback_disabled": True,
        }
    ]
    tables["mls_source_map_nodes"][0]["source_id"] = "other-source"

    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client(tables)).resolve(_ref())

    assert raised.value.code == SourceContextErrorCode.INVALID_REFERENCE


def test_resolver_requires_specific_physical_and_map_identity():
    bad = SourceSpineRef(logical_source_id="costanzo-physiology")
    with pytest.raises(SourceContextUnavailable) as raised:
        SupabaseHoc90SourceContextResolver(Client({})).resolve(bad)

    assert raised.value.code == SourceContextErrorCode.INVALID_REFERENCE
