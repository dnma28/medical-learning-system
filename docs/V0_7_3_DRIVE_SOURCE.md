# v0.7.3 — Google Drive runtime source fetcher

The compiler can now receive a private Google Drive PDF without requiring a
permanent local library.

```text
Google Drive
    ↓ metadata + canDownload check
temporary private PDF
    ↓
IncrementalSourceCompiler
    ↓
Coverage / Evidence / Alignment / Manifest
    ↓
temporary PDF deleted
```

## Download contract

The fetcher follows Google Drive v3 blob-download behavior:

- fetch metadata first;
- require `application/pdf`;
- require `capabilities.canDownload=true`;
- use `files.get_media` for the blob;
- stream into a temporary file;
- verify byte size when Drive exposes `size`;
- delete the temporary file on success or failure.

The compiler still calculates SHA-256 and remains the authority for exact
content-version deduplication.

## Authentication

The runtime service supports two backend-only credential paths:

1. `MLS_GOOGLE_DRIVE_OAUTH_JSON` containing an authorized-user credential;
2. Google Application Default Credentials.

Only the read-only Drive scope is requested.

The application performs no interactive OAuth browser flow. Provisioning the
credential is a deployment concern and the credential must live in the cloud
secret store.

The ChatGPT Google Drive connection is separate and is not reused as runtime
OAuth for this repository.

## Install

Google Drive runtime support is optional:

```bash
pip install -e ".[google-drive]"
```

CI uses a fake Drive service and downloads nothing.

## Current boundary

v0.7.3 provides safe source materialization. A later worker milestone will
atomically claim cloud queue jobs, fetch the corresponding source, invoke the
compiler, and finish/retry the job.
