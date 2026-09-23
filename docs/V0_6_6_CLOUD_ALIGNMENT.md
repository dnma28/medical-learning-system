# v0.6.6 — Cloud alignment links in retrieval

## Derived links are first-class data

Evidence content remains immutable source extraction. Evidence-to-structure
alignment is stored separately in `mls_evidence_structure_links`.

The link table is derived and can be regenerated after a Coverage structure
refresh.

## Why retrieval returns a set of structure nodes

One evidence block can legitimately map to:

- a section;
- its parent chapter;
- an exact heading plus ancestors;
- multiple conservative page-range candidates when the source layout is
  ambiguous.

Retrieval therefore returns:

```text
structure_node_ids = [...]
```

rather than choosing one arbitrary node.

## Benchmark semantics

A retrieval hit occupies one rank regardless of how many structure links it
has. Structure MRR asks whether any node attached to that hit intersects the
gold structure set.

This prevents ancestor/candidate links from artificially consuming multiple
ranks.

## Supabase security

The new link table follows the existing backend-only policy:

- RLS enabled;
- anon/authenticated access revoked;
- service-role only;
- evidence and structure foreign keys cascade because links are derived data.

## Retrieval RPCs

Both keyword and semantic RPCs aggregate all links for each evidence hit and
order them by confidence, then Coverage depth.

No fuzzy alignment or Canonical KG promotion occurs in this layer.
