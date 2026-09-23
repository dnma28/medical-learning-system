from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from .relation_support import (
    RelationAuditLink,
    RelationAuditMappingState,
)


class RelationAuditDecisionRecord(BaseModel):
    decision_id: str = Field(min_length=1)
    mapping_id: str = Field(min_length=1)
    relation_candidate_id: str = Field(min_length=1)
    audit_id: str = Field(min_length=1)
    state: RelationAuditMappingState
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    note: str | None = None
    supersedes_decision_id: str | None = None

    @model_validator(mode="after")
    def reviewed_state_only(self) -> "RelationAuditDecisionRecord":
        if self.state == RelationAuditMappingState.UNREVIEWED:
            raise ValueError("UNREVIEWED is not a persisted review decision")
        return self


def make_relation_audit_decision(
    link: RelationAuditLink,
    *,
    supersedes_decision_id: str | None = None,
) -> RelationAuditDecisionRecord:
    if link.state == RelationAuditMappingState.UNREVIEWED:
        raise ValueError("relation audit link must be reviewed before persistence")
    if not link.reviewer or link.reviewed_at is None:
        raise ValueError("reviewed relation audit link needs reviewer and reviewed_at")

    identity = json.dumps(
        {
            "mapping_id": link.mapping_id,
            "relation_candidate_id": link.relation_candidate_id,
            "audit_id": link.audit_id,
            "state": link.state.value,
            "reviewer": link.reviewer,
            "reviewed_at": link.reviewed_at.isoformat(),
            "note": link.note,
            "supersedes_decision_id": supersedes_decision_id,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return RelationAuditDecisionRecord(
        decision_id=f"rel-audit-decision-{digest}",
        mapping_id=link.mapping_id,
        relation_candidate_id=link.relation_candidate_id,
        audit_id=link.audit_id,
        state=link.state,
        reviewer=link.reviewer,
        reviewed_at=link.reviewed_at,
        note=link.note,
        supersedes_decision_id=supersedes_decision_id,
    )


class RelationAuditDecisionStore:
    """Append-only SQLite ledger for relation↔claim-audit review decisions."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS relation_audit_decisions (
                    decision_id TEXT PRIMARY KEY,
                    mapping_id TEXT NOT NULL,
                    relation_candidate_id TEXT NOT NULL,
                    audit_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    note TEXT,
                    supersedes_decision_id TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_relation_audit_mapping_history
                ON relation_audit_decisions(mapping_id, reviewed_at, decision_id)
                """
            )

    def append(self, record: RelationAuditDecisionRecord) -> None:
        with self._connect() as connection:
            if record.supersedes_decision_id is not None:
                prior = connection.execute(
                    """
                    SELECT mapping_id FROM relation_audit_decisions
                    WHERE decision_id = ?
                    """,
                    (record.supersedes_decision_id,),
                ).fetchone()
                if prior is None:
                    raise ValueError(
                        "supersedes_decision_id does not exist: "
                        f"{record.supersedes_decision_id}"
                    )
                if prior["mapping_id"] != record.mapping_id:
                    raise ValueError(
                        "superseded decision belongs to a different mapping"
                    )
            try:
                connection.execute(
                    """
                    INSERT INTO relation_audit_decisions (
                        decision_id, mapping_id, relation_candidate_id,
                        audit_id, state, reviewer, reviewed_at,
                        note, supersedes_decision_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.decision_id,
                        record.mapping_id,
                        record.relation_candidate_id,
                        record.audit_id,
                        record.state.value,
                        record.reviewer,
                        record.reviewed_at.isoformat(),
                        record.note,
                        record.supersedes_decision_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"decision_id already exists: {record.decision_id}"
                ) from exc

    def get(self, decision_id: str) -> RelationAuditDecisionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM relation_audit_decisions
                WHERE decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
        return self._row(row) if row is not None else None

    def history(self, mapping_id: str) -> list[RelationAuditDecisionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM relation_audit_decisions
                WHERE mapping_id = ?
                ORDER BY reviewed_at, decision_id
                """,
                (mapping_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def latest(self, mapping_id: str) -> RelationAuditDecisionRecord | None:
        history = self.history(mapping_id)
        return history[-1] if history else None

    @staticmethod
    def _row(row: sqlite3.Row) -> RelationAuditDecisionRecord:
        return RelationAuditDecisionRecord(
            decision_id=row["decision_id"],
            mapping_id=row["mapping_id"],
            relation_candidate_id=row["relation_candidate_id"],
            audit_id=row["audit_id"],
            state=RelationAuditMappingState(row["state"]),
            reviewer=row["reviewer"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
            note=row["note"],
            supersedes_decision_id=row["supersedes_decision_id"],
        )
