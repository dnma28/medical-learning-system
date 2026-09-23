# Supabase runtime smoke test

This workflow validates only the backend runtime credential pair:

- `MLS_SUPABASE_URL`
- `MLS_SUPABASE_SECRET_KEY`

It performs an authenticated read-only request to the Supabase REST endpoint.

It does **not**:

- run SQL;
- create tables;
- apply migrations;
- print credentials;
- test Google Drive access.

Database migration deployment is intentionally separate because the Supabase CLI
requires database/CLI deployment credentials in addition to the application
secret key.
