from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .source_catalog import CatalogSource, SourceCatalog


IDENTITY_FIELDS = frozenset({"edition", "publication_year", "identity_status"})
PROVENANCE_NAMESPACE = "source_identity_reconciliation_v2_policy"


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _without_updated_at(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "updated_at"}


def _validate_identity_patch(identity_patch: dict[str, Any]) -> None:
    unexpected = sorted(set(identity_patch) - IDENTITY_FIELDS)
    if unexpected:
        raise ValueError(f"identity patch contains non-allowlisted fields: {unexpected}")


@dataclass(frozen=True)
class IdentityCorrectionPlan:
    logical_source_id: str
    before_row_sha256: str
    before_updated_at: str
    identity_patch: dict[str, Any]
    metadata_namespace: str
    metadata_value: dict[str, Any]
    physical_sources_sha256: str
    staging_rows_sha256: str
    certificate_rows_sha256: str
    expected_after_business_row: dict[str, Any]
    expected_after_business_sha256: str
    rollback: dict[str, Any]
    catalog_patch: dict[str, Any] | None = None

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def prepare_catalog_identity_patch(
    catalog: SourceCatalog,
    *,
    logical_source_id: str,
    identity_patch: dict[str, Any],
) -> dict[str, Any]:
    """Prepare one catalog identity change without mutating the catalog.

    This deliberately cannot touch notes, matching/provider bindings, role, domain,
    kind, or Source Map state. It is a pure preparation helper; callers decide
    separately whether a reviewed YAML edit is authorized.
    """
    _validate_identity_patch(identity_patch)
    source = catalog.get(logical_source_id)
    before = source.model_dump(mode="json")
    candidate = copy.deepcopy(before)
    candidate.update(identity_patch)
    after = CatalogSource.model_validate(candidate).model_dump(mode="json")

    protected = set(before) - IDENTITY_FIELDS
    changed_protected = sorted(
        field for field in protected if before.get(field) != after.get(field)
    )
    if changed_protected:
        raise ValueError(
            f"catalog identity patch changed protected fields: {changed_protected}"
        )

    return {
        "logical_source_id": logical_source_id,
        "before": before,
        "after": after,
        "changed_fields": sorted(
            field
            for field in IDENTITY_FIELDS
            if before.get(field) != after.get(field)
        ),
    }


def prepare_identity_correction(
    *,
    logical_row: dict[str, Any],
    expected_before_sha256: str,
    identity_patch: dict[str, Any],
    metadata_value: dict[str, Any],
    physical_sources: list[dict[str, Any]],
    staging_rows: list[dict[str, Any]],
    certificate_rows: list[dict[str, Any]],
    metadata_namespace: str = PROVENANCE_NAMESPACE,
    catalog: SourceCatalog | None = None,
    catalog_identity_patch: dict[str, Any] | None = None,
) -> IdentityCorrectionPlan:
    """Prepare a guarded one-book correction plan without performing a write.

    Input list order is intentionally preserved in guard digests. Some historical
    source manifests use non-sorted physical-source order and must remain exactly
    reproducible.
    """
    _validate_identity_patch(identity_patch)

    logical_source_id = logical_row.get("logical_source_id")
    if not isinstance(logical_source_id, str) or not logical_source_id:
        raise ValueError("logical row requires logical_source_id")

    updated_at = logical_row.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at:
        raise ValueError("logical row requires an exact updated_at preimage")

    before_sha256 = canonical_json_sha256(logical_row)
    if before_sha256 != expected_before_sha256:
        raise ValueError(
            "logical row preimage drifted: "
            f"expected {expected_before_sha256}, got {before_sha256}"
        )

    metadata = logical_row.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("logical row metadata must be an object")
    if metadata_namespace in metadata:
        raise ValueError(
            f"metadata namespace already exists: {metadata_namespace}"
        )

    expected_after = copy.deepcopy(logical_row)
    expected_after.update(identity_patch)
    expected_metadata = copy.deepcopy(metadata)
    expected_metadata[metadata_namespace] = copy.deepcopy(metadata_value)
    expected_after["metadata"] = expected_metadata

    # The database owns updated_at, so the durable after-state comparison excludes
    # only that timestamp. Every business field remains part of the CAS guard.
    expected_after_business = _without_updated_at(expected_after)
    expected_after_business_sha256 = canonical_json_sha256(expected_after_business)

    catalog_plan = None
    if catalog is not None:
        catalog_plan = prepare_catalog_identity_patch(
            catalog,
            logical_source_id=logical_source_id,
            identity_patch=catalog_identity_patch or identity_patch,
        )

    rollback = {
        "expected_after_business_sha256": expected_after_business_sha256,
        "require_recorded_server_updated_at": True,
        "restore_identity_fields": {
            field: copy.deepcopy(logical_row.get(field))
            for field in sorted(identity_patch)
        },
        "restore_metadata_preimage": copy.deepcopy(metadata),
        "stop_on_concurrent_change": True,
    }

    return IdentityCorrectionPlan(
        logical_source_id=logical_source_id,
        before_row_sha256=before_sha256,
        before_updated_at=updated_at,
        identity_patch=copy.deepcopy(identity_patch),
        metadata_namespace=metadata_namespace,
        metadata_value=copy.deepcopy(metadata_value),
        physical_sources_sha256=canonical_json_sha256(physical_sources),
        staging_rows_sha256=canonical_json_sha256(staging_rows),
        certificate_rows_sha256=canonical_json_sha256(certificate_rows),
        expected_after_business_row=expected_after_business,
        expected_after_business_sha256=expected_after_business_sha256,
        rollback=rollback,
        catalog_patch=catalog_plan,
    )
