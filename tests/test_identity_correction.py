from pathlib import Path

import pytest

from medical_learning_system.identity_correction import (
    PROVENANCE_NAMESPACE,
    canonical_json_sha256,
    prepare_catalog_identity_patch,
    prepare_identity_correction,
)
from medical_learning_system.source_catalog import SourceCatalog


CATALOG = Path("data/sources/core_library.yaml")


def logical_row():
    return {
        "logical_source_id": "costanzo-physiology",
        "title": "Costanzo Physiology",
        "kind": "textbook",
        "domain": "physiology",
        "edition": "6",
        "publication_year": None,
        "role": "concise mechanism clarification and physiology support",
        "identity_status": "verify_from_source",
        "source_map_state": "ready_for_hoc90",
        "metadata": {
            "notes": ["preserve me"],
            "promoted_history": {"version": 1},
        },
        "updated_at": "2026-09-27T14:41:26.925447+00:00",
        "source_map_version": 1,
        "promoted_staging_version": 3,
        "promoted_certificate_sha256": "a" * 64,
    }


def physical_source(source_id="source-a", logical_source_id="costanzo-physiology"):
    return {
        "source_id": source_id,
        "logical_source_id": logical_source_id,
        "content_sha256": "b" * 64,
    }


def stage(version=3, logical_source_id="costanzo-physiology"):
    return {
        "logical_source_id": logical_source_id,
        "staging_version": version,
        "payload_sha256": "c" * 64,
    }


def certificate(version=3, logical_source_id="costanzo-physiology"):
    return {
        "logical_source_id": logical_source_id,
        "staging_version": version,
        "certificate_sha256": "d" * 64,
    }


def test_prepare_identity_correction_preserves_metadata_and_runtime_fields():
    before = logical_row()
    plan = prepare_identity_correction(
        logical_row=before,
        expected_before_sha256=canonical_json_sha256(before),
        identity_patch={
            "edition": "6",
            "publication_year": 2018,
            "identity_status": "verified",
        },
        metadata_value={
            "publication_year_status": "source_established",
            "certified_fields": ["edition", "publication_year"],
        },
        physical_sources=[physical_source()],
        staging_rows=[stage()],
        certificate_rows=[certificate()],
    )

    after = plan.expected_after_business_row
    assert after["publication_year"] == 2018
    assert after["identity_status"] == "verified"
    assert after["source_map_version"] == 1
    assert after["promoted_staging_version"] == 3
    assert after["promoted_certificate_sha256"] == "a" * 64
    assert after["metadata"]["notes"] == ["preserve me"]
    assert after["metadata"]["promoted_history"] == {"version": 1}
    assert after["metadata"][PROVENANCE_NAMESPACE][
        "publication_year_status"
    ] == "source_established"
    assert "updated_at" not in after

    assert plan.rollback["restore_identity_fields"] == {
        "edition": "6",
        "identity_status": "verify_from_source",
        "publication_year": None,
    }
    assert plan.rollback["restore_metadata_preimage"] == before["metadata"]
    assert plan.rollback["stop_on_concurrent_change"] is True


def test_prepare_identity_correction_rejects_preimage_drift():
    before = logical_row()
    with pytest.raises(ValueError, match="preimage drifted"):
        prepare_identity_correction(
            logical_row=before,
            expected_before_sha256="0" * 64,
            identity_patch={"identity_status": "verified"},
            metadata_value={"status": "reviewed"},
            physical_sources=[],
            staging_rows=[],
            certificate_rows=[],
        )


def test_prepare_identity_correction_rejects_existing_namespace():
    before = logical_row()
    before["metadata"][PROVENANCE_NAMESPACE] = {"old": True}
    with pytest.raises(ValueError, match="namespace already exists"):
        prepare_identity_correction(
            logical_row=before,
            expected_before_sha256=canonical_json_sha256(before),
            identity_patch={"identity_status": "verified"},
            metadata_value={"status": "reviewed"},
            physical_sources=[],
            staging_rows=[],
            certificate_rows=[],
        )


def test_identity_patch_cannot_touch_runtime_or_metadata_directly():
    before = logical_row()
    for forbidden in ("source_map_state", "metadata", "title"):
        with pytest.raises(ValueError, match="non-allowlisted"):
            prepare_identity_correction(
                logical_row=before,
                expected_before_sha256=canonical_json_sha256(before),
                identity_patch={forbidden: "bad"},
                metadata_value={"status": "reviewed"},
                physical_sources=[],
                staging_rows=[],
                certificate_rows=[],
            )


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"edition": ""}, "edition"),
        ({"publication_year": "2018"}, "publication_year"),
        ({"publication_year": 1700}, "publication_year"),
        ({"identity_status": "made_up"}, "identity_status"),
    ],
)
def test_identity_patch_values_are_validated(patch, message):
    before = logical_row()
    with pytest.raises(ValueError, match=message):
        prepare_identity_correction(
            logical_row=before,
            expected_before_sha256=canonical_json_sha256(before),
            identity_patch=patch,
            metadata_value={"status": "reviewed"},
            physical_sources=[],
            staging_rows=[],
            certificate_rows=[],
        )


def test_guard_rows_must_belong_to_exact_logical_book():
    before = logical_row()
    with pytest.raises(ValueError, match="does not belong"):
        prepare_identity_correction(
            logical_row=before,
            expected_before_sha256=canonical_json_sha256(before),
            identity_patch={},
            metadata_value={"status": "reviewed"},
            physical_sources=[physical_source(logical_source_id="other-book")],
            staging_rows=[],
            certificate_rows=[],
        )


def test_guard_digests_preserve_input_order():
    before = logical_row()
    first = [physical_source("b"), physical_source("a")]
    second = list(reversed(first))

    plan_a = prepare_identity_correction(
        logical_row=before,
        expected_before_sha256=canonical_json_sha256(before),
        identity_patch={},
        metadata_value={"status": "reviewed"},
        physical_sources=first,
        staging_rows=[],
        certificate_rows=[],
    )
    plan_b = prepare_identity_correction(
        logical_row=before,
        expected_before_sha256=canonical_json_sha256(before),
        identity_patch={},
        metadata_value={"status": "reviewed"},
        physical_sources=second,
        staging_rows=[],
        certificate_rows=[],
    )

    assert plan_a.physical_sources_sha256 != plan_b.physical_sources_sha256


def test_explicit_empty_catalog_patch_is_not_replaced_by_identity_patch():
    before = logical_row()
    catalog = SourceCatalog.load(CATALOG)
    plan = prepare_identity_correction(
        logical_row=before,
        expected_before_sha256=canonical_json_sha256(before),
        identity_patch={"identity_status": "verified"},
        metadata_value={"status": "reviewed"},
        physical_sources=[physical_source()],
        staging_rows=[],
        certificate_rows=[],
        catalog=catalog,
        catalog_identity_patch={},
    )

    assert plan.catalog_patch is not None
    assert plan.catalog_patch["changed_fields"] == []


def test_scoped_catalog_patch_preserves_non_identity_fields():
    catalog = SourceCatalog.load(CATALOG)
    plan = prepare_catalog_identity_patch(
        catalog,
        logical_source_id="magee-orthopedic-physical-assessment",
        identity_patch={
            "edition": "7",
            "publication_year": 2021,
            "identity_status": "verified",
        },
    )

    before = plan["before"]
    after = plan["after"]
    assert before["notes"] == after["notes"]
    assert before["match_patterns"] == after["match_patterns"]
    assert before["part_pattern"] == after["part_pattern"]
    assert before["provider_file_ids"] == after["provider_file_ids"]
    assert before["source_map_state"] == after["source_map_state"] == "deep_anchored"
    assert after["edition"] == "7"
    assert after["publication_year"] == 2021
    assert after["identity_status"] == "verified"
    assert set(plan["changed_fields"]) == {
        "edition",
        "publication_year",
        "identity_status",
    }


def test_prepare_identity_correction_rejects_non_policy_namespace():
    before = logical_row()
    with pytest.raises(ValueError, match="reviewed policy namespace"):
        prepare_identity_correction(
            logical_row=before,
            expected_before_sha256=canonical_json_sha256(before),
            identity_patch={"identity_status": "verified"},
            metadata_value={"status": "reviewed"},
            physical_sources=[],
            staging_rows=[],
            certificate_rows=[],
            metadata_namespace="unreviewed_namespace",
        )
