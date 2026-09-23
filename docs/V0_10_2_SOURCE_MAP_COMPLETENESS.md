# v0.10.2 Source Map completeness

`LogicalSourceMap.completeness()` is a read-only gate over explicit Source Map data. It does not create mappings or promote `source_map_state`.

The report excludes the BOOK root from structural coverage and records:

- number of structural nodes;
- nodes with an explicit `source_id`;
- node IDs whose physical source remains unknown;
- page locators with a known start but unknown end;
- whether every structural node has explicit physical-source provenance.

`ready_for_hoc90` is false for a BOOK-only map and whenever any structural node lacks `source_id`. An open-ended page range is reported but is not guessed or automatically completed. A node may legitimately be source-anchored without a page locator when the verified source identity is known but finer localization is not yet available.

This report measures Source Map completeness only. It is not learner mastery, evidence quality, Candidate/Canonical KG status, or a medical-truth signal. Missing values remain unknown until verified from source material.
