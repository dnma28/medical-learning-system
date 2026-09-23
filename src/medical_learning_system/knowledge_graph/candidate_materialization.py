from __future__ import annotations

from pydantic import BaseModel, Field

from ..evidence_store import SourceEvidenceBlock
from .claim_audit import ClaimAuditRecord, assess_claim_audit
from .schemas import (
    Evidence,
    GraphEdge,
    GraphNode,
    SourceLocator,
    ValidationStatus,
)
from .v5_migration import (
    RelationKind,
    V5NodeCandidate,
    V5RelationCandidate,
)
from .validation import validate_for_promotion


class CandidateMaterializationError(ValueError):
    pass


class ExplicitRelationAuditBinding(BaseModel):
    relation_candidate_id: str = Field(min_length=1)
    audit_id: str = Field(min_length=1)


class CandidateCanonicalReviewDecision(BaseModel):
    eligible_for_human_review: bool
    reasons: tuple[str, ...]


def materialize_v5_node(
    node: V5NodeCandidate,
    *,
    patch_id: str,
) -> GraphNode:
    """Create a typed candidate node without inventing semantic type/evidence."""
    label = (
        node.labels.get("vi")
        or node.labels.get("en")
        or node.labels.get("label")
        or node.labels.get("name")
        or node.node_id
    )
    aliases = [
        value
        for key, value in node.labels.items()
        if value != label and key in {"vi", "en", "label", "name"}
    ]
    return GraphNode(
        id=node.node_id,
        label=label,
        node_type="legacy_v5_candidate",
        aliases=aliases,
        metadata={
            "legacy_patch_id": patch_id,
            "legacy_raw": node.raw,
        },
        validation_status=ValidationStatus.CANDIDATE,
        evidence=[],
    )


def materialize_v5_relation(
    relation: V5RelationCandidate,
    *,
    patch_id: str,
) -> GraphEdge:
    """Create a typed relation candidate with no claim evidence by default."""
    return GraphEdge(
        id=relation.candidate_id,
        source=relation.source,
        relation=relation.relation,
        target=relation.target,
        metadata={
            "legacy_patch_id": patch_id,
            "relation_kind": relation.kind.value,
            "legacy_provenance": relation.provenance,
            "legacy_raw": relation.raw,
        },
        validation_status=ValidationStatus.CANDIDATE,
        evidence=[],
    )


def bind_audit_to_candidate_edge(
    edge: GraphEdge,
    *,
    relation: V5RelationCandidate,
    audit: ClaimAuditRecord,
    binding: ExplicitRelationAuditBinding,
    evidence_by_id: dict[str, SourceEvidenceBlock],
) -> GraphEdge:
    """Attach reviewed evidence only through an explicit relation↔audit binding."""
    if edge.id != relation.candidate_id:
        raise CandidateMaterializationError(
            "edge does not represent the supplied relation candidate"
        )
    if binding.relation_candidate_id != relation.candidate_id:
        raise CandidateMaterializationError(
            "binding relation_candidate_id does not match relation"
        )
    if binding.audit_id != audit.audit_id:
        raise CandidateMaterializationError(
            "binding audit_id does not match claim audit"
        )

    audit_decision = assess_claim_audit(audit)
    if not audit_decision.source_grounded_ready:
        raise CandidateMaterializationError(
            "claim audit is not source-grounded ready: "
            + ",".join(audit_decision.reasons)
        )

    missing = sorted(
        evidence_id
        for evidence_id in audit.selected_evidence_ids
        if evidence_id not in evidence_by_id
    )
    if missing:
        raise CandidateMaterializationError(
            "selected evidence blocks are unavailable: " + ",".join(missing)
        )

    evidence = [
        _graph_evidence(audit, evidence_by_id[evidence_id])
        for evidence_id in sorted(audit.selected_evidence_ids)
    ]
    metadata = dict(edge.metadata)
    metadata.update(
        {
            "claim_audit_id": audit.audit_id,
            "claim_source_anchor_id": audit.source_anchor_id,
            "source_anchor_state": audit.source_anchor_state.value,
            "content_fidelity_state": audit.content_fidelity_state.value,
            "current_validity_state": audit.current_validity_state.value,
            "requires_current_check": audit.requires_current_check,
            "review_method": audit.review_method,
        }
    )
    return edge.model_copy(
        update={
            "metadata": metadata,
            "evidence": evidence,
            "validation_status": ValidationStatus.CANDIDATE,
        }
    )


def assess_candidate_for_canonical_review(
    edge: GraphEdge,
    *,
    relation: V5RelationCandidate,
    audit: ClaimAuditRecord,
) -> CandidateCanonicalReviewDecision:
    """Assess eligibility for human review; never performs promotion."""
    reasons: list[str] = []

    structural = validate_for_promotion(edge)
    reasons.extend(f"structural:{reason}" for reason in structural.reasons)

    audit_decision = assess_claim_audit(audit)
    if not audit_decision.source_grounded_ready:
        reasons.append("claim_not_source_grounded")

    if (
        audit.requires_current_check
        and not audit_decision.current_standard_ready
    ):
        reasons.append("current_validity_not_verified")

    if relation.kind == RelationKind.BRIDGE:
        reasons.append("bridge_requires_separate_inference_review")
    if (relation.provenance or "").upper() == "INFERRED":
        reasons.append("inferred_relation_not_direct_source_fact")

    if edge.metadata.get("claim_audit_id") != audit.audit_id:
        reasons.append("edge_not_bound_to_claim_audit")
    if edge.id != relation.candidate_id:
        reasons.append("edge_relation_identity_mismatch")

    unique = tuple(sorted(set(reasons)))
    return CandidateCanonicalReviewDecision(
        eligible_for_human_review=not unique,
        reasons=unique,
    )


def _graph_evidence(
    audit: ClaimAuditRecord,
    block: SourceEvidenceBlock,
) -> Evidence:
    return Evidence(
        locator=SourceLocator(
            source_id=block.source_id,
            page=block.pdf_page,
            quote_hash=block.content_sha256,
        ),
        claim_text=audit.claim_text,
        extractor=f"claim-audit:{audit.audit_id}",
    )
