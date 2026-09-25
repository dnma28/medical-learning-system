# Source Map scope policy

Status: canonical Source Map milestone policy

## Authoritative TOC denominator

`toc_denominator` counts required navigable structural identities in the textbook hierarchy.

Included by default:
- Part / Unit
- Chapter
- Section
- Subsection
- required appendices or answer-key containers/children when they are treated as navigable book content

Excluded by default:
- book root
- index entries/reference index pages
- figure/table captions
- non-hierarchical pedagogical supplements such as clinical boxes, case callouts, sample problems, and similar inserts that are not part of the source TOC/section hierarchy

A supplement is included in the denominator only when the source itself treats it as a structural TOC/hierarchy identity.

Exclusion from `toc_denominator` is not omission. Pedagogically relevant supplemental elements must be preserved in a separate auditable supplemental index/ledger with source locators and provenance when they are needed for navigation or teaching.

## Evidence rules

- Original textbook/PDF is source of truth.
- Internal source evidence overrides filename assumptions.
- Candidate count or bookmark count is never a denominator.
- Point heading locator is not a section range.
- Never infer `page_end`.
- PART/UNIT hierarchy must not be flattened.
- Every denominator inclusion/exclusion must be explainable from source structure.

## Certification interaction

The current staging validator requires every staged proposal node to be required and verified, and the number of non-book required nodes to equal `toc_denominator`. Therefore supplemental non-denominator elements remain in sidecar evidence/index artifacts under the current schema rather than being inserted as non-required staging nodes.

If a future schema supports supplemental nodes directly, they may be imported without changing `toc_denominator` unless their source classification changes.

## Costanzo 6e application

Current Costanzo v3 contains:
- 881 main-text structural identities
- 13 required appendix/answer-key identities
- 5 excluded publication/front-matter observations
- Book root excluded from denominator

Thus the structural denominator candidate remains **N=894**.

A follow-up source scan found:
- 35 unique numbered Clinical Physiology BOX identities (36 visual label observations because BOX 7.1 continues across two pages)
- 26 SAMPLE PROBLEM starts

These are substantial pedagogical elements but are not present in the printed chapter TOCs or native structural outline. Under this policy they belong in a supplemental teaching-element ledger and do not increase `toc_denominator`.

This policy does not by itself certify Costanzo. Independent review must still verify the supplemental ledger, confirm that no additional structural heading classes were omitted, and attest the exact immutable staging version/digest before certification.
