# v0.7.1 — Cloud compiler parity

The incremental compiler no longer depends on concrete SQLite classes.

It consumes small storage protocols:

```text
SourceRegistryBackend
CoverageBackend
EvidenceBackend
AlignmentBackend
ManifestBackend
```

SQLite classes satisfy these protocols directly.

Supabase uses thin adapters only where the existing cloud method names differ:

```text
SupabaseMedicalStore
  ├── SupabaseRegistryAdapter
  ├── CoverageBackend (direct)
  └── SupabaseEvidenceAdapter

SupabaseAlignmentStore
  └── AlignmentBackend

SupabaseCompilationManifestStore
  └── ManifestBackend
```

This keeps compilation policy independent from the database.

## Cloud manifest

Migration `0004_compilation_manifests.sql` stores the same content-version
identity as SQLite:

```text
(source_id, content_sha256, strategy)
```

A successful row is therefore sufficient to recognize an already compiled byte
version on another worker or a later session.

## Security

The manifest table follows the existing backend-only Supabase model:

- RLS enabled
- anon/authenticated revoked
- service_role only
- no credentials in Git

## Still required for a real cloud worker

The backend must still obtain a temporary private local path for the source PDF
from Google Drive before calling the compiler. The ChatGPT Drive connector is
not treated as application runtime OAuth.
