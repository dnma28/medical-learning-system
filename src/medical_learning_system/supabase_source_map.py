from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .source_catalog import CatalogSource, SourceCatalog
from .source_map import LogicalSourceMap, SourceMapNode
from .source_map_staging import StagingSourceMap


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


class SupabaseSourceMapStore:
    LOGICAL_SOURCES = "mls_logical_sources"
    SOURCE_MAP_NODES = "mls_source_map_nodes"
    STAGING = "mls_source_map_staging"

    def __init__(self, client: Any):
        self.client = client

    def upsert_catalog(self, catalog: SourceCatalog) -> int:
        rows = [_catalog_source_to_row(source) for source in catalog.sources]
        if not rows:
            return 0
        (
            self.client.table(self.LOGICAL_SOURCES)
            .upsert(rows, on_conflict="logical_source_id")
            .execute()
        )
        return len(rows)

    def get_logical_source(self, logical_source_id: str) -> dict[str, Any] | None:
        response = (
            self.client.table(self.LOGICAL_SOURCES)
            .select("*")
            .eq("logical_source_id", logical_source_id)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return dict(rows[0]) if rows else None

    def replace_source_map(self, source_map: LogicalSourceMap) -> int:
        # PostgREST executes delete, upsert, and state updates in separate
        # transactions. An error after delete would leave a partial/empty map.
        # Keep production imports disabled until a staging-backed RPC performs
        # validation, version guard, and replacement in one database transaction.
        raise RuntimeError(
            "Source Map replacement requires audited staging and an atomic "
            "version-guarded promotion RPC"
        )

    def stage_source_map(self, staged: StagingSourceMap) -> str:
        """Atomically allocate and insert one immutable draft version."""
        payload = staged.model_dump(mode="json")
        response = self.client.rpc("mls_stage_source_map", {
            "p_logical_source_id": staged.logical_source_id,
            "p_expected_latest_staging_version": staged.staging_version - 1,
            "p_proposal": payload["proposal"],
            "p_toc_denominator": payload["toc_denominator"],
            "p_extraction_version": payload["extraction_version"],
            "p_source_manifest": payload["source_manifest"],
            "p_audit_metadata": payload["audit_metadata"],
        }).execute()
        result = response.data
        if not isinstance(result, dict):
            raise RuntimeError("staging RPC readback missing")
        if result.get("staging_version") != staged.staging_version:
            raise RuntimeError("staging version readback mismatch")
        digest = result.get("payload_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise RuntimeError("staging digest readback missing")
        return digest

    def claim_source_map_work(
        self, *, work_key: str, logical_source_id: str, batch_id: str,
        owner_id: str, scope_sha256: str, manifest_sha256: str,
        lease_seconds: int = 1800,
    ) -> dict[str, Any]:
        response = self.client.rpc("mls_claim_source_map_work", {
            "p_work_key": work_key,
            "p_logical_source_id": logical_source_id,
            "p_batch_id": batch_id,
            "p_owner_id": owner_id,
            "p_scope_sha256": scope_sha256,
            "p_manifest_sha256": manifest_sha256,
            "p_lease_seconds": lease_seconds,
        }).execute()
        if not isinstance(response.data, dict) or response.data.get("status") != "active":
            raise RuntimeError("Source Map work lease readback missing")
        return dict(response.data)

    def heartbeat_source_map_work(
        self, *, work_key: str, lease_token: str, lease_seconds: int = 1800,
    ) -> str:
        response = self.client.rpc("mls_heartbeat_source_map_work", {
            "p_work_key": work_key,
            "p_lease_token": lease_token,
            "p_lease_seconds": lease_seconds,
        }).execute()
        if not isinstance(response.data, str):
            raise RuntimeError("Source Map work heartbeat readback missing")
        return response.data

    def complete_source_map_work(
        self, *, work_key: str, lease_token: str,
        artifact_ref: str, artifact_sha256: str,
    ) -> None:
        response = self.client.rpc("mls_complete_source_map_work", {
            "p_work_key": work_key,
            "p_lease_token": lease_token,
            "p_artifact_ref": artifact_ref,
            "p_artifact_sha256": artifact_sha256,
        }).execute()
        if response.data is not True:
            raise RuntimeError("Source Map work completion readback mismatch")

    def release_source_map_work(self, *, work_key: str, lease_token: str) -> None:
        response = self.client.rpc("mls_release_source_map_work", {
            "p_work_key": work_key,
            "p_lease_token": lease_token,
        }).execute()
        if response.data is not True:
            raise RuntimeError("Source Map work release readback mismatch")

    def certify_source_map(
        self, logical_source_id: str, staging_version: int, expected_staging_sha256: str
    ) -> str:
        response = self.client.rpc("mls_certify_source_map", {
            "p_logical_source_id": logical_source_id,
            "p_staging_version": staging_version,
            "p_expected_staging_sha256": expected_staging_sha256,
        }).execute()
        if not isinstance(response.data, str) or len(response.data) != 64:
            raise RuntimeError("certificate digest missing")
        return response.data

    def promote_source_map(
        self, logical_source_id: str, staging_version: int,
        certificate_sha256: str, expected_version: int,
    ) -> int:
        response = self.client.rpc("mls_promote_source_map", {
            "p_logical_source_id": logical_source_id,
            "p_staging_version": staging_version,
            "p_certificate_sha256": certificate_sha256,
            "p_expected_version": expected_version,
        }).execute()
        version = response.data
        if version != expected_version + 1:
            raise RuntimeError("promotion version readback mismatch")
        source = self.get_logical_source(logical_source_id)
        stage_response = (
            self.client.table(self.STAGING).select("proposal")
            .eq("logical_source_id", logical_source_id)
            .eq("staging_version", staging_version).limit(1).execute()
        )
        stages = _data(stage_response)
        if (source is None or source.get("source_map_version") != version
                or source.get("promoted_staging_version") != staging_version
                or source.get("promoted_certificate_sha256") != certificate_sha256
                or len(stages) != 1):
            raise RuntimeError("promotion metadata readback mismatch")
        expected = sorted(
            (node["node_id"] for node in stages[0]["proposal"])
        )
        actual = sorted(row["node_id"] for row in self.get_source_map(logical_source_id))
        if actual != expected:
            raise RuntimeError("promoted map readback mismatch")
        return version

    def get_readiness(self, logical_source_id: str) -> dict[str, Any]:
        response = self.client.rpc(
            "mls_source_map_readiness", {"p_logical_source_id": logical_source_id}
        ).execute()
        if not isinstance(response.data, dict):
            raise RuntimeError("audited readiness response missing")
        return dict(response.data)

    def get_source_map(self, logical_source_id: str) -> list[dict[str, Any]]:
        response = (
            self.client.table(self.SOURCE_MAP_NODES)
            .select("*")
            .eq("logical_source_id", logical_source_id)
            .order("order_index")
            .execute()
        )
        return [dict(row) for row in _data(response)]


def _catalog_source_to_row(source: CatalogSource) -> dict[str, Any]:
    return {
        "logical_source_id": source.logical_source_id,
        "title": source.title,
        "kind": source.kind.value,
        "domain": source.domain,
        "edition": source.edition,
        "publication_year": source.publication_year,
        "role": source.role,
        "identity_status": source.identity_status.value,
        "source_map_state": source.source_map_state.value,
        "metadata": {
            "notes": source.notes,
            "match_patterns": source.match_patterns,
            "part_pattern": source.part_pattern,
            "canonical_provider_file_id": source.canonical_provider_file_id,
            "alternate_provider_file_ids": source.alternate_provider_file_ids,
        },
        "updated_at": _utcnow(),
    }


def _source_map_node_to_row(node: SourceMapNode) -> dict[str, Any]:
    return {
        "logical_source_id": node.logical_source_id,
        "node_id": node.node_id,
        "parent_id": node.parent_id,
        "source_id": node.source_id,
        "kind": node.kind.value,
        "title": node.title,
        "depth": node.depth,
        "order_index": node.order_index,
        "page_start": node.page_start,
        "page_end": node.page_end,
        "source_anchor": node.source_anchor,
        "learning_value": node.learning_value.value if node.learning_value else None,
        "freshness_required": node.freshness_required,
        "updated_at": _utcnow(),
    }
