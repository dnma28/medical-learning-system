from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MigrationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RelationKind(str, Enum):
    ASSERTED = "asserted"
    GUARD = "guard"
    BRIDGE = "bridge"


class MigrationFinding(BaseModel):
    code: str
    severity: MigrationSeverity
    message: str


class ExtractedJsonObject(BaseModel):
    object_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    payload: dict[str, Any]


class V5NodeCandidate(BaseModel):
    node_id: str = Field(min_length=1)
    labels: dict[str, str] = Field(default_factory=dict)
    raw: dict[str, Any]


class V5RelationCandidate(BaseModel):
    candidate_id: str
    source: str
    relation: str
    target: str
    kind: RelationKind
    provenance: str | None = None
    raw: Any
    object_index: int


class V5PatchMigration(BaseModel):
    document_name: str
    raw_text: str
    objects: list[ExtractedJsonObject]
    patch_ids: list[str]
    quality_states: list[str]
    migration_states: list[str]
    truth_rules: list[str]
    nodes: list[V5NodeCandidate]
    relations: list[V5RelationCandidate]
    source_anchors: list[dict[str, Any]]
    claim_verification: list[dict[str, Any]]
    hoc90_payloads: list[dict[str, Any]]
    error_graph_payloads: list[list[Any]]
    findings: list[MigrationFinding]
    external_endpoint_ids: set[str]


class V5CorpusMigrationReport(BaseModel):
    documents: int
    json_objects: int
    unique_patch_ids: int
    nodes: int
    relations: int
    relation_kinds: dict[str, int]
    findings: list[MigrationFinding]
    duplicate_patch_ids: dict[str, list[str]]
    duplicate_node_ids: dict[str, list[str]]


class V5PatchParseError(ValueError):
    pass


def extract_json_objects(text: str) -> list[ExtractedJsonObject]:
    results: list[ExtractedJsonObject] = []
    index = 0

    while index < len(text):
        if text[index] != "{":
            index += 1
            continue

        start = index
        depth = 0
        in_string = False
        escaped = False
        cursor = start

        while cursor < len(text):
            char = text[cursor]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        raw = text[start : cursor + 1]
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError as exc:
                            raise V5PatchParseError(
                                f"invalid JSON object at offset {start}: {exc.msg}"
                            ) from exc
                        if not isinstance(payload, dict):
                            raise V5PatchParseError("top-level JSON must be an object")
                        results.append(
                            ExtractedJsonObject(
                                object_index=len(results),
                                start=start,
                                end=cursor + 1,
                                payload=payload,
                            )
                        )
                        index = cursor + 1
                        break
            cursor += 1
        else:
            raise V5PatchParseError(
                f"unterminated JSON object starting at offset {start}"
            )

    if not results:
        raise V5PatchParseError("no JSON object found in patch document")
    return results


def migrate_v5_patch_text(document_name: str, text: str) -> V5PatchMigration:
    objects = extract_json_objects(text)
    findings: list[MigrationFinding] = []
    patch_ids = _strings(objects, "patch_id")
    quality_states = _strings(objects, "quality_state")
    migration_states = _strings(objects, "migration_state")
    truth_rules = _strings(objects, "truth_rule")

    if not patch_ids:
        findings.append(MigrationFinding(
            code="missing_patch_id",
            severity=MigrationSeverity.WARNING,
            message="No patch_id was present in the document.",
        ))

    nodes: list[V5NodeCandidate] = []
    relations: list[V5RelationCandidate] = []
    source_anchors: list[dict[str, Any]] = []
    claim_verification: list[dict[str, Any]] = []
    hoc90_payloads: list[dict[str, Any]] = []
    error_graph_payloads: list[list[Any]] = []

    patch_key = patch_ids[0] if patch_ids else document_name
    for item in objects:
        payload = item.payload
        nodes.extend(_nodes(payload, findings))
        relations.extend(_relations(payload, item.object_index, patch_key, findings))
        source_anchors.extend(_dict_list(payload.get("source_anchors")))
        claim_verification.extend(_dict_list(payload.get("claim_verification")))
        if isinstance(payload.get("hoc90_core"), dict):
            hoc90_payloads.append(payload["hoc90_core"])
        if isinstance(payload.get("error_graph"), list):
            error_graph_payloads.append(payload["error_graph"])

    node_counts = Counter(node.node_id for node in nodes)
    for node_id, count in node_counts.items():
        if count > 1:
            findings.append(MigrationFinding(
                code="duplicate_node_id_in_document",
                severity=MigrationSeverity.ERROR,
                message=f"Node ID {node_id!r} appears {count} times.",
            ))

    local_ids = set(node_counts)
    endpoints = {
        endpoint
        for relation in relations
        for endpoint in (relation.source, relation.target)
    }
    external = endpoints - local_ids
    if external:
        findings.append(MigrationFinding(
            code="external_relation_endpoints",
            severity=MigrationSeverity.INFO,
            message=(
                f"{len(external)} endpoint IDs are external to this patch and "
                "require corpus-level resolution."
            ),
        ))

    inferred = [
        relation for relation in relations
        if relation.kind == RelationKind.BRIDGE
        and (relation.provenance or "").upper() == "INFERRED"
    ]
    if inferred:
        findings.append(MigrationFinding(
            code="inferred_bridges_preserved",
            severity=MigrationSeverity.INFO,
            message=f"{len(inferred)} inferred bridge relation(s) preserved.",
        ))

    return V5PatchMigration(
        document_name=document_name,
        raw_text=text,
        objects=objects,
        patch_ids=patch_ids,
        quality_states=quality_states,
        migration_states=migration_states,
        truth_rules=truth_rules,
        nodes=nodes,
        relations=relations,
        source_anchors=source_anchors,
        claim_verification=claim_verification,
        hoc90_payloads=hoc90_payloads,
        error_graph_payloads=error_graph_payloads,
        findings=findings,
        external_endpoint_ids=external,
    )


def audit_v5_corpus(migrations: list[V5PatchMigration]) -> V5CorpusMigrationReport:
    patch_docs: dict[str, list[str]] = defaultdict(list)
    node_docs: dict[str, list[str]] = defaultdict(list)
    findings: list[MigrationFinding] = []

    for migration in migrations:
        findings.extend(migration.findings)
        for patch_id in set(migration.patch_ids):
            patch_docs[patch_id].append(migration.document_name)
        for node_id in {node.node_id for node in migration.nodes}:
            node_docs[node_id].append(migration.document_name)

    duplicate_patch_ids = {
        key: sorted(value) for key, value in patch_docs.items() if len(value) > 1
    }
    duplicate_node_ids = {
        key: sorted(value) for key, value in node_docs.items() if len(value) > 1
    }

    for key, docs in duplicate_patch_ids.items():
        findings.append(MigrationFinding(
            code="duplicate_patch_id_across_documents",
            severity=MigrationSeverity.ERROR,
            message=f"Patch ID {key!r} occurs in: {', '.join(docs)}",
        ))

    for key, docs in duplicate_node_ids.items():
        findings.append(MigrationFinding(
            code="node_id_reused_across_documents",
            severity=MigrationSeverity.INFO,
            message=(
                f"Node ID {key!r} is reused across: {', '.join(docs)}. "
                "Do not auto-deduplicate it."
            ),
        ))

    kinds = Counter(
        relation.kind.value
        for migration in migrations
        for relation in migration.relations
    )
    return V5CorpusMigrationReport(
        documents=len(migrations),
        json_objects=sum(len(item.objects) for item in migrations),
        unique_patch_ids=len(patch_docs),
        nodes=sum(len(item.nodes) for item in migrations),
        relations=sum(len(item.relations) for item in migrations),
        relation_kinds=dict(kinds),
        findings=findings,
        duplicate_patch_ids=duplicate_patch_ids,
        duplicate_node_ids=duplicate_node_ids,
    )


def _nodes(
    payload: dict[str, Any],
    findings: list[MigrationFinding],
) -> list[V5NodeCandidate]:
    raw_nodes = payload.get("nodes")
    if raw_nodes is None:
        return []
    if not isinstance(raw_nodes, list):
        findings.append(MigrationFinding(
            code="nodes_not_list",
            severity=MigrationSeverity.ERROR,
            message="nodes is not a list; raw payload remains preserved.",
        ))
        return []

    output: list[V5NodeCandidate] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            findings.append(MigrationFinding(
                code="invalid_node_shape",
                severity=MigrationSeverity.ERROR,
                message="A node entry has no usable string id.",
            ))
            continue
        labels = {
            key: value for key, value in raw.items()
            if key in {"vi", "en", "label", "name"} and isinstance(value, str)
        }
        output.append(V5NodeCandidate(
            node_id=raw["id"].strip(),
            labels=labels,
            raw=raw,
        ))
    return output


def _relations(
    payload: dict[str, Any],
    object_index: int,
    patch_key: str,
    findings: list[MigrationFinding],
) -> list[V5RelationCandidate]:
    output: list[V5RelationCandidate] = []
    for field, kind in (
        ("edges", RelationKind.ASSERTED),
        ("guards", RelationKind.GUARD),
    ):
        values = payload.get(field)
        if values is None:
            continue
        if not isinstance(values, list):
            findings.append(MigrationFinding(
                code=f"{field}_not_list",
                severity=MigrationSeverity.ERROR,
                message=f"{field} is not a list.",
            ))
            continue
        for position, raw in enumerate(values):
            triple = _triple(raw)
            if triple is None:
                findings.append(MigrationFinding(
                    code=f"invalid_{field}_shape",
                    severity=MigrationSeverity.ERROR,
                    message=f"{field}[{position}] is not a valid triple.",
                ))
                continue
            output.append(_make_relation(
                patch_key, object_index, position, *triple, kind, None, raw
            ))

    bridges = payload.get("bridges")
    if isinstance(bridges, list):
        for position, raw in enumerate(bridges):
            if not isinstance(raw, dict):
                continue
            values = (raw.get("from"), raw.get("relation"), raw.get("to"))
            if not all(isinstance(value, str) and value.strip() for value in values):
                findings.append(MigrationFinding(
                    code="invalid_bridge_shape",
                    severity=MigrationSeverity.ERROR,
                    message=f"bridges[{position}] lacks from/relation/to.",
                ))
                continue
            provenance = raw.get("provenance")
            output.append(_make_relation(
                patch_key,
                object_index,
                position,
                values[0].strip(),
                values[1].strip(),
                values[2].strip(),
                RelationKind.BRIDGE,
                provenance.strip() if isinstance(provenance, str) else None,
                raw,
            ))
    return output


def _make_relation(
    patch_key: str,
    object_index: int,
    position: int,
    source: str,
    relation: str,
    target: str,
    kind: RelationKind,
    provenance: str | None,
    raw: Any,
) -> V5RelationCandidate:
    value = (
        f"{patch_key}|{object_index}|{position}|{kind.value}|"
        f"{source}|{relation}|{target}"
    )
    digest = hashlib.sha256(value.encode()).hexdigest()[:20]
    return V5RelationCandidate(
        candidate_id=f"v5rel-{digest}",
        source=source,
        relation=relation,
        target=target,
        kind=kind,
        provenance=provenance,
        raw=raw,
        object_index=object_index,
    )


def _triple(raw: Any) -> tuple[str, str, str] | None:
    if not isinstance(raw, list) or len(raw) != 3:
        return None
    if not all(isinstance(value, str) and value.strip() for value in raw):
        return None
    return raw[0].strip(), raw[1].strip(), raw[2].strip()


def _strings(objects: list[ExtractedJsonObject], field: str) -> list[str]:
    return [
        value.strip()
        for item in objects
        if isinstance((value := item.payload.get(field)), str) and value.strip()
    ]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
