# v0.5 — Evidence Store

## Purpose

The Evidence Store is the reusable parsed-source layer.

```text
PDF
 ↓ parse once
SourceEvidenceBlock
 ↓ persist
EvidenceStore
 ↓ reuse many times
retrieval / validation / HỌC90
```

This is how the project avoids re-reading or re-parsing the same textbook every
study session.

## Evidence block vs medical claim

These are deliberately different objects.

**SourceEvidenceBlock**
- a parsed block from a source;
- may be text, image, table, equation or code;
- is not automatically a medical fact.

**Knowledge Graph claim evidence**
- supports a proposed medical node/edge or assertion;
- must reference source provenance;
- still passes Candidate → Validation → Canonical rules.

The Evidence Store has no method that writes into the Canonical Medical KG.

## Provenance retained

Each block keeps:

- physical source_id
- optional Coverage structure node
- parser block index
- parser page index (0-based)
- derived physical PDF page (1-based)
- optional printed page label
- modality
- parser/version
- optional bounding box
- content fingerprint

## Refresh behavior

Parsed evidence is replace-by-source. Re-parsing one changed source removes its
obsolete blocks but cannot affect evidence belonging to another source.

This layer contains operational extracted data and belongs in local/cloud
storage, not in the Git repository.
