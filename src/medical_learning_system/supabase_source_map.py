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
        """Insert one immutable draft version; unresolved nodes stay in staging."""
        row = staged.model_dump(mode="json")
        response = self.client.table(self.STAGING).insert(row).execute()
        rows = _data(response)
        if len(rows) != 1 or not rows[0].get("payload_sha256"):
            raise RuntimeError("staging insert has no digest readback")
        return str(rows[0]["payload_sha256"])

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
