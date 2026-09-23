import pytest

from medical_learning_system.knowledge_graph.v5_migration import (
    MigrationSeverity,
    RelationKind,
    V5PatchParseError,
    audit_v5_corpus,
    extract_json_objects,
    migrate_v5_patch_text,
)


HOMEOSTASIS = """
{
  "patch_id":"foundation.homeostasis.v1",
  "quality_state":"SOURCE_VERIFIED",
  "nodes":[
    {"id":"regulated-variable","vi":"biến được điều hòa","en":"regulated variable"},
    {"id":"negative-feedback","vi":"phản hồi âm","en":"negative feedback"}
  ],
  "edges":[
    ["negative-feedback","opposes_deviation_of","regulated-variable"]
  ],
  "guards":[
    ["homeostasis","not_equivalent_to","static_constancy"]
  ],
  "sources":[{"book":"Guyton","chapter":"Ch 1"}]
}

MIGRATION v5.3
{
  "migration_state":"PARTIAL_SOURCE_AUDIT",
  "truth_rule":"original source file overrides this patch",
  "source_anchors":[
    {
      "id":"sa-b04-ch1-homeostasis",
      "source_book_id":"b04",
      "chapter":"1",
      "pdf_page_range":"19-27",
      "verification_state":"PASS"
    }
  ],
  "claim_verification":[
    {
      "claim":"homeostasis is dynamic rather than static constancy",
      "source_anchor_id":"sa-b04-ch1-homeostasis",
      "verification_state":"PASS"
    },
    {
      "claim":"generic sensor-controller-effector chain",
      "verification_state":"GAP"
    }
  ]
}
"""

BRIDGE = """
{
  "patch_id":"bridge.pharmacology_rehab_dose_response.v1",
  "quality_state":"CORPUS_DERIVED",
  "nodes":[
    {"id":"potency","vi":"potency","en":"potency"},
    {"id":"efficacy","vi":"efficacy","en":"efficacy"}
  ],
  "edges":[["potency","describes","dose-needed"]],
  "bridges":[
    {
      "from":"pharmacology-dose-response",
      "to":"rehab-exercise-prescription",
      "relation":"shared reasoning pattern",
      "provenance":"INFERRED"
    }
  ],
  "guards":[["potency","not_equivalent_to","efficacy"]],
  "hoc90_core":{"feynman_prompt":"Explain potency versus efficacy."},
  "error_graph":[
    {"error":"lower EC50 means greater maximal effect","correction":"greater potency"}
  ]
}
"""


def test_extracts_multiple_json_objects_from_mixed_document():
    objects = extract_json_objects(HOMEOSTASIS)
    assert len(objects) == 2
    assert objects[0].payload["patch_id"] == "foundation.homeostasis.v1"
    assert objects[1].payload["migration_state"] == "PARTIAL_SOURCE_AUDIT"


def test_preserves_nodes_guards_anchors_and_truth_rule():
    result = migrate_v5_patch_text("homeostasis", HOMEOSTASIS)

    assert result.patch_ids == ["foundation.homeostasis.v1"]
    assert result.quality_states == ["SOURCE_VERIFIED"]
    assert result.migration_states == ["PARTIAL_SOURCE_AUDIT"]
    assert result.truth_rules == ["original source file overrides this patch"]
    assert {node.node_id for node in result.nodes} == {
        "regulated-variable",
        "negative-feedback",
    }
    assert len(result.source_anchors) == 1
    assert len(result.claim_verification) == 2
    assert {relation.kind for relation in result.relations} == {
        RelationKind.ASSERTED,
        RelationKind.GUARD,
    }


def test_inferred_bridge_remains_inferred():
    result = migrate_v5_patch_text("bridge", BRIDGE)
    bridge = next(
        relation for relation in result.relations
        if relation.kind == RelationKind.BRIDGE
    )
    assert bridge.provenance == "INFERRED"
    assert result.hoc90_payloads
    assert result.error_graph_payloads
    assert any(
        finding.code == "inferred_bridges_preserved"
        and finding.severity == MigrationSeverity.INFO
        for finding in result.findings
    )


def test_unknown_fields_are_preserved():
    text = '{"patch_id":"p1","mystery":{"nested":[1,2,3]}}'
    result = migrate_v5_patch_text("patch", text)
    assert result.objects[0].payload["mystery"] == {"nested": [1, 2, 3]}
    assert result.raw_text == text


def test_invalid_json_is_not_repaired():
    with pytest.raises(V5PatchParseError):
        migrate_v5_patch_text("bad", '{"patch_id":"bad","nodes":[}')


def test_duplicate_node_is_reported_not_deduplicated():
    result = migrate_v5_patch_text(
        "dup",
        '{"patch_id":"dup.v1","nodes":[{"id":"x"},{"id":"x"}]}',
    )
    assert len(result.nodes) == 2
    assert any(
        finding.code == "duplicate_node_id_in_document"
        for finding in result.findings
    )


def test_corpus_audit_reports_cross_patch_reuse_without_merging():
    first = migrate_v5_patch_text(
        "a",
        '{"patch_id":"a.v1","nodes":[{"id":"shared"}]}',
    )
    second = migrate_v5_patch_text(
        "b",
        '{"patch_id":"b.v1","nodes":[{"id":"shared"}]}',
    )
    report = audit_v5_corpus([first, second])
    assert report.documents == 2
    assert report.nodes == 2
    assert report.duplicate_node_ids == {"shared": ["a", "b"]}
