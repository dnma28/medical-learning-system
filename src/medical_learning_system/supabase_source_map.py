from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .source_catalog import CatalogSource, SourceCatalog
from .source_map import LogicalSourceMap, SourceMapNode


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


class SupabaseSourceMapStore:
    LOGICAL_SOURCES = "mls_logical_sources"
    SOURCE_MAP_NODES = "mls_source_map_nodes"

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
        # A Source Map is a derived navigation artifact. Replacing the map must
        # not delete physical source evidence or Canonical Medical KG data.
        (
            self.client.table(self.SOURCE_MAP_NODES)
            .delete()
            .eq("logical_source_id", source_map.logical_source_id)
            .execute()
        )

        ordered = sorted(source_map.nodes, key=lambda node: node.order_index)
        if ordered:
            (
                self.client.table(self.SOURCE_MAP_NODES)
                .upsert(
                    [_source_map_node_to_row(node) for node in ordered],
                    on_conflict="logical_source_id,node_id",
                )
                .execute()
            )

        (
            self.client.table(self.LOGICAL_SOURCES)
            .update(
                {
                    "source_map_state": source_map.state.value,
                    "updated_at": _utcnow(),
                }
            )
            .eq("logical_source_id", source_map.logical_source_id)
            .execute()
        )
        return len(ordered)

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
        "learning_value": node.learning_value.value,
        "freshness_required": node.freshness_required,
        "updated_at": _utcnow(),
    }
