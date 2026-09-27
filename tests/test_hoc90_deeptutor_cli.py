from medical_learning_system.cli.hoc90_deeptutor import _readiness


class Response:
    def __init__(self, data, *, count=None):
        self.data = data
        self.count = count


class Query:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters = []
        self.in_filters = []
        self.limit_count = None
        self.order_field = None
        self.order_desc = False
        self.want_count = False

    def select(self, _fields, count=None):
        self.want_count = count == "exact"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, set(values)))
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def execute(self):
        rows = [
            row
            for row in self.rows
            if all(row.get(field) == value for field, value in self.filters)
            and all(row.get(field) in values for field, values in self.in_filters)
        ]
        if self.order_field:
            rows.sort(
                key=lambda row: row.get(self.order_field),
                reverse=self.order_desc,
            )
        exact_count = len(rows) if self.want_count else None
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return Response([dict(row) for row in rows], count=exact_count)


class Rpc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return Response(self.data)


class Client:
    def __init__(self, tables, readiness):
        self.tables = tables
        self.readiness = readiness

    def table(self, name):
        return Query(self.tables.get(name, []))

    def rpc(self, name, params):
        assert name == "mls_source_map_readiness"
        assert params["p_logical_source_id"] == "costanzo-physiology"
        return Rpc(self.readiness)


def base_tables():
    return {
        "mls_hoc90_blueprints": [
            {
                "lesson_id": "pilot",
                "status": "active",
                "curriculum_position": "physiology/cellular",
                "updated_at": "2026-09-27T03:00:00Z",
            }
        ],
        "mls_learning_sessions": [
            {
                "session_id": "session",
                "status": "active",
                "topic": "Cellular physiology",
                "updated_at": "2026-09-27T03:00:00Z",
            }
        ],
        "mls_logical_sources": [
            {
                "logical_source_id": "costanzo-physiology",
                "title": "Costanzo Physiology",
                "source_map_state": "unmapped",
                "source_map_version": 1,
            }
        ],
        "mls_source_map_evidence_links": [
            {
                "logical_source_id": "costanzo-physiology",
                "evidence_id": "ev-1",
            }
        ],
    }


def test_readiness_uses_audited_rpc_not_historical_source_map_label():
    result = _readiness(
        Client(
            base_tables(),
            {
                "logical_source_id": "costanzo-physiology",
                "ready_for_hoc90": True,
                "audited_state": "ready_for_hoc90",
                "current_version": 1,
            },
        ),
        "costanzo-physiology",
    )

    assert result["ready"] is True
    assert result["blockers"] == []
    assert result["source_map_readiness"]["ready_for_hoc90"] is True


def test_readiness_requires_evidence_for_requested_logical_source():
    tables = base_tables()
    tables["mls_source_map_evidence_links"] = [
        {
            "logical_source_id": "kandel-principles-neural-science",
            "evidence_id": "other",
        }
    ]
    result = _readiness(
        Client(
            tables,
            {
                "logical_source_id": "costanzo-physiology",
                "ready_for_hoc90": True,
                "current_version": 1,
            },
        ),
        "costanzo-physiology",
    )

    assert result["ready"] is False
    assert "no_exact_source_map_evidence" in result["blockers"]
