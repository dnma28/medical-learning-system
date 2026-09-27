# HỌC90 promoted Source Map evidence bridge

## Why this exists

The original evidence alignment table points to legacy `mls_structure_nodes`. Promoted
Source Maps use `mls_source_map_nodes` with different stable node identities. HỌC90
therefore needs a separate link layer rather than pretending the two structures are the
same.

`mls_source_map_evidence_links` is derived runtime evidence. It is not medical truth,
curriculum, learner state, or a Source Map certificate.

## Compile contract

The source-map-aware compiler:

1. requires `mls_source_map_readiness(...).ready_for_hoc90=true`;
2. reads the promoted Source Map version;
3. materializes the exact registered Drive PDF privately;
4. hashes the bytes and requires equality with `mls_sources.content_sha256`;
5. extracts native PDF text blocks with page/bounding-box provenance;
6. aligns those blocks to promoted heading points using deterministic exact/prefix/heading
   sequence logic;
7. writes reusable evidence blocks and the dedicated Source Map evidence links;
8. never infers or writes Source Map `page_end`;
9. never changes KG, curriculum, learner state, Error Graph, Skill Tree, or M0–M7.

If evidence already exists for a physical source, replacement requires the explicit
`--allow-replace-existing` flag.

## Resolver order

HỌC90 source-context resolution uses:

1. exact `mls_source_map_evidence_links` for logical source + physical source + node;
2. legacy exact `mls_evidence_structure_links` for backward compatibility;
3. legacy scalar `structure_node_id` only when exact;
4. otherwise `SOURCE_GAP`.

No semantic-search fallback is allowed inside this exact-node resolver.

## Manual production workflow

The workflow `HOC90 source-map evidence pilot` is manual only. It requires backend
Supabase credentials and read-only Google Drive OAuth in GitHub secrets. It defaults to
Costanzo as the pilot logical source but performs no automatic run on push.

Multi-file books require an explicit physical `source_id`.

Raw textbook bytes remain outside Git.
