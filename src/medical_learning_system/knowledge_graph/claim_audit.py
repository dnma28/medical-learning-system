from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class SourceAnchorState(str, Enum):
    PASS = "PASS"
    MISMATCH = "MISMATCH"
    GAP = "GAP"


class ContentFidelityState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    WRONG_SOURCE = "WRONG_SOURCE"
    UNRESOLVED = "UNRESOLVED"


class CurrentValidityState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BOOK_CURRENT_UNCHECKED = "BOOK_CURRENT_UNCHECKED"
    REQUIRES_EXTERNAL_CHECK = "REQUIRES_EXTERNAL_CHECK"
    CURRENT_VERIFIED = "CURRENT_VERIFIED"
    OUTDATED = "OUTDATED"
    CONTESTED = "CONTESTED"


class ClaimAuditRecord(BaseModel):
    audit_id: str = Field(min_length=1)
    patch_id: str = Field(min_length=1)
    claim_text: str = Field(min_length=1)
    source_anchor_id: str = Field(min_length=1)
    source_anchor_state: SourceAnchorState
    evidence_candidate_ids: set[str] = Field(default_factory=set)
    selected_evidence_ids: set[str] = Field(default_factory=set)
    content_fidelity_state: ContentFidelityState
    current_validity_state: CurrentValidityState
    requires_current_check: bool = False
    reviewer: str = Field(min_length=1)
    review_method: str = Field(min_length=1)
    reviewed_at: datetime
    supersedes_audit_id: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selected_evidence(self) -> "ClaimAuditRecord":
        if not self.selected_evidence_ids.issubset(self.evidence_candidate_ids):
            raise ValueError(
                "selected_evidence_ids must be a subset of evidence_candidate_ids"
            )
        if (
            self.content_fidelity_state == ContentFidelityState.VERIFIED
            and not self.selected_evidence_ids
        ):
            raise ValueError(
                "VERIFIED content fidelity requires selected evidence"
            )
        return self


class ClaimAuditDecision(BaseModel):
    source_grounded_ready: bool
    current_standard_ready: bool
    reasons: tuple[str, ...]


def assess_claim_audit(record: ClaimAuditRecord) -> ClaimAuditDecision:
    reasons: list[str] = []

    if record.source_anchor_state != SourceAnchorState.PASS:
        reasons.append("source_anchor_not_pass")
    if record.content_fidelity_state != ContentFidelityState.VERIFIED:
        reasons.append("content_fidelity_not_verified")
    if not record.selected_evidence_ids:
        reasons.append("missing_selected_evidence")

    source_grounded_ready = not reasons

    current_reasons = list(reasons)
    if record.requires_current_check:
        if record.current_validity_state != CurrentValidityState.CURRENT_VERIFIED:
            current_reasons.append("current_validity_not_verified")
    else:
        if record.current_validity_state not in {
            CurrentValidityState.NOT_APPLICABLE,
            CurrentValidityState.CURRENT_VERIFIED,
        }:
            current_reasons.append("current_standard_not_established")

    return ClaimAuditDecision(
        source_grounded_ready=source_grounded_ready,
        current_standard_ready=not current_reasons,
        reasons=tuple(sorted(set(current_reasons))),
    )


def make_claim_audit(
    *,
    patch_id: str,
    claim_text: str,
    source_anchor_id: str,
    source_anchor_state: SourceAnchorState,
    evidence_candidate_ids: set[str],
    selected_evidence_ids: set[str],
    content_fidelity_state: ContentFidelityState,
    current_validity_state: CurrentValidityState,
    requires_current_check: bool,
    reviewer: str,
    review_method: str,
    reviewed_at: datetime,
    supersedes_audit_id: str | None = None,
    notes: list[str] | None = None,
) -> ClaimAuditRecord:
    identity = json.dumps(
        {
            "patch_id": patch_id,
            "claim_text": claim_text,
            "source_anchor_id": source_anchor_id,
            "source_anchor_state": source_anchor_state.value,
            "selected_evidence_ids": sorted(selected_evidence_ids),
            "content_fidelity_state": content_fidelity_state.value,
            "current_validity_state": current_validity_state.value,
            "requires_current_check": requires_current_check,
            "reviewer": reviewer,
            "review_method": review_method,
            "reviewed_at": reviewed_at.isoformat(),
            "supersedes_audit_id": supersedes_audit_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return ClaimAuditRecord(
        audit_id=f"audit-{digest}",
        patch_id=patch_id,
        claim_text=claim_text,
        source_anchor_id=source_anchor_id,
        source_anchor_state=source_anchor_state,
        evidence_candidate_ids=evidence_candidate_ids,
        selected_evidence_ids=selected_evidence_ids,
        content_fidelity_state=content_fidelity_state,
        current_validity_state=current_validity_state,
        requires_current_check=requires_current_check,
        reviewer=reviewer,
        review_method=review_method,
        reviewed_at=reviewed_at,
        supersedes_audit_id=supersedes_audit_id,
        notes=notes or [],
    )


class ClaimAuditStore:
    """Append-only SQLite history for claim audit decisions."""

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
                CREATE TABLE IF NOT EXISTS claim_audits (
                    audit_id TEXT PRIMARY KEY,
                    patch_id TEXT NOT NULL,
                    claim_text TEXT NOT NULL,
                    source_anchor_id TEXT NOT NULL,
                    source_anchor_state TEXT NOT NULL,
                    evidence_candidate_ids_json TEXT NOT NULL,
                    selected_evidence_ids_json TEXT NOT NULL,
                    content_fidelity_state TEXT NOT NULL,
                    current_validity_state TEXT NOT NULL,
                    requires_current_check INTEGER NOT NULL,
                    reviewer TEXT NOT NULL,
                    review_method TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    supersedes_audit_id TEXT,
                    notes_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_claim_audits_claim
                ON claim_audits(patch_id, claim_text, reviewed_at)
                """
            )

    def append(self, record: ClaimAuditRecord) -> None:
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO claim_audits (
                        audit_id, patch_id, claim_text, source_anchor_id,
                        source_anchor_state, evidence_candidate_ids_json,
                        selected_evidence_ids_json, content_fidelity_state,
                        current_validity_state, requires_current_check,
                        reviewer, review_method, reviewed_at,
                        supersedes_audit_id, notes_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.audit_id,
                        record.patch_id,
                        record.claim_text,
                        record.source_anchor_id,
                        record.source_anchor_state.value,
                        json.dumps(sorted(record.evidence_candidate_ids)),
                        json.dumps(sorted(record.selected_evidence_ids)),
                        record.content_fidelity_state.value,
                        record.current_validity_state.value,
                        int(record.requires_current_check),
                        record.reviewer,
                        record.review_method,
                        record.reviewed_at.isoformat(),
                        record.supersedes_audit_id,
                        json.dumps(record.notes, ensure_ascii=False),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"audit_id already exists: {record.audit_id}"
                ) from exc

    def history(self, patch_id: str, claim_text: str) -> list[ClaimAuditRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM claim_audits
                WHERE patch_id = ? AND claim_text = ?
                ORDER BY reviewed_at, audit_id
                """,
                (patch_id, claim_text),
            ).fetchall()
        return [self._row(row) for row in rows]

    def latest(
        self,
        patch_id: str,
        claim_text: str,
    ) -> ClaimAuditRecord | None:
        history = self.history(patch_id, claim_text)
        return history[-1] if history else None

    @staticmethod
    def _row(row: sqlite3.Row) -> ClaimAuditRecord:
        return ClaimAuditRecord(
            audit_id=row["audit_id"],
            patch_id=row["patch_id"],
            claim_text=row["claim_text"],
            source_anchor_id=row["source_anchor_id"],
            source_anchor_state=SourceAnchorState(row["source_anchor_state"]),
            evidence_candidate_ids=set(
                json.loads(row["evidence_candidate_ids_json"])
            ),
            selected_evidence_ids=set(
                json.loads(row["selected_evidence_ids_json"])
            ),
            content_fidelity_state=ContentFidelityState(
                row["content_fidelity_state"]
            ),
            current_validity_state=CurrentValidityState(
                row["current_validity_state"]
            ),
            requires_current_check=bool(row["requires_current_check"]),
            reviewer=row["reviewer"],
            review_method=row["review_method"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
            supersedes_audit_id=row["supersedes_audit_id"],
            notes=json.loads(row["notes_json"]),
        )
