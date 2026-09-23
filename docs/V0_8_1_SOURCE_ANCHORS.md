# v0.8.1 — KG v5 source-anchor resolution

This layer links legacy v5 source anchors to the current Source Registry and
Evidence Store without guessing.

## Explicit legacy mappings

The initial mapping registry contains only identities directly verified in
connected KG v5 patch metadata:

- b04 → guyton-hall-physiology
- b08 → costanzo-physiology

b06 is intentionally unresolved in this slice.

## Resolution sequence

legacy source_book_id
→ explicit mapping registry
→ logical_source_id
→ exact registered physical source
→ exact edition when supplied
→ explicit PDF page locators
→ stored SourceEvidenceBlock IDs

Filename similarity is not used to choose between physical sources.

## Verification is independent

A source anchor can resolve to the correct PDF and evidence blocks while its
legacy verification state remains GAP or MISMATCH.

Canonical evidence readiness requires both:
1. legacy anchor state PASS;
2. at least one evidence block resolved from an explicit PDF page locator.

Identity resolution never upgrades a legacy verification state.

## Page policy

The resolver accepts only explicit physical PDF locators already present in the
anchor, including pdf_page, pdf_pages, pdf_start_page and a strict numeric
pdf_page_range such as 19-27.

Chapter or section text is not converted into a guessed page number.
