from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .source_catalog import CatalogSource, IdentityStatus, SourceCatalog


IDENTITY_FIELDS = frozenset({"edition", "publication_year", "identity_status"})
PROVENANCE_NAMESPACE = "source_identity_reconciliation_v2_policy"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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

    if "edition" in identity_patch:
        edition = identity_patch["edition"]
        if edition is not None and (
            not isinstance(edition, str) or not edition.strip()
        ):
            raise ValueError("edition must be a non-empty string or null")

    if "publication_year" in identity_patch:
        year = identity_patch["publication_year"]
        if year is not None and (
            isinstance(year, bool)
            or not isinstance(year, int)
            or year < 1800
            or year > 2200
        ):
            raise ValueError("publication_year must be an integer from 1800 to 2200 or null")

    if "identity_status" in identity_patch:
        status = identity_patch["identity_status"]
        if not isinstance(status, str):
            raise ValueError("identity_status must be a string enum value")
        try:
            IdentityStatus(status)
        except ValueError as exc:
            raise ValueError(f"invalid identity_status: {status!r}") from exc


def _validate_guard_rows(
    rows: list[dict[str, Any]],
    *,
    logical_source_id: str,
    label: str,
) -> None:
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        if row.get("logical_source_id") != logical_source_id:
            raise ValueError(
                f"{label}[{index}] does not belong to {logical_source_id}"
            )


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

    Guard inputs are full rows for the same logical book. Input list order is
    intentionally preserved in digests because historical source manifests can
    use a non-sorted physical-source order that must remain reproducible.
    """
    _validate_identity_patch(identity_patch)

    if not _SHA256_RE.fullmatch(expected_before_sha256):
        raise ValueError("expected_before_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(metadata_value, dict):
        raise ValueError("metadata_value must be an object")
    if not isinstance(metadata_namespace, str) or not metadata_namespace.strip():
        raise ValueError("metadata_namespace must be a non-empty string")
    if metadata_namespace != PROVENANCE_NAMESPACE:
        raise ValueError("metadata_namespace must match the reviewed policy namespace")

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

    _validate_guard_rows(
        physical_sources,
        logical_source_id=logical_source_id,
        label="physical_sources",
    )
    _validate_guard_rows(
        staging_rows,
        logical_source_id=logical_source_id,
        label="staging_rows",
    )
    _validate_guard_rows(
        certificate_rows,
        logical_source_id=logical_source_id,
        label="certificate_rows",
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
        patch_for_catalog = (
            identity_patch
            if catalog_identity_patch is None
            else catalog_identity_patch
        )
        catalog_plan = prepare_catalog_identity_patch(
            catalog,
            logical_source_id=logical_source_id,
            identity_patch=patch_for_catalog,
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
