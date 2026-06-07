# Phase 71 Audit Retention Contract

**Status:** Planned
**Created:** 2026-06-07

## Purpose

Define how audit evidence can be represented for stronger retention without storing raw private report artifacts or claiming compliance-grade immutability prematurely.

## Audit Classes

Supported classes:

- Report recovery operations.
- Recovery jobs and targets.
- Generation retry and resend actions.
- Report edit and artifact edit actions.
- Artifact rollback actions.
- Release evidence validation and safe-fixture status checks.
- Support handoff package generation/refusal.

## Retention Manifest Shape

Required top-level fields:

| Field | Required | Notes |
|-------|----------|-------|
| `schema_version` | Yes | Start with `v1`. |
| `manifest_id` | Yes | Opaque generated id. |
| `generated_at` | Yes | ISO-8601 UTC timestamp. |
| `generated_by` | Yes | Admin/support-safe operator identifier. |
| `scope` | Yes | Audit class and bounded reference ids. |
| `retention_category` | Yes | Operational, incident, release, fixture, or support handoff. |
| `retention_clock` | Yes | Event timestamp source and retention start. |
| `items` | Yes | Metadata-only evidence item summaries. |
| `verification` | Yes | Counts, hashes, missing refs, skipped refs, privacy result. |
| `status` | Yes | `sealed`, `unsealed`, `partial`, `refused`, or `unsupported`. |

## Privacy Boundary

Retention manifests must not include:

- S3 keys or bucket/object paths for private report artifacts.
- Presigned URLs.
- Raw report JSON or HTML.
- Raw artifact payloads.
- Auth tokens, passwords, cookies, AWS keys, or session secrets.

## Phase 72 Constraints

- Generate bounded manifests from explicit references.
- Prefer hashes of canonical metadata summaries over raw payload storage.
- Refuse destructive retention operations.
- Record redacted audit metadata for manifest generation/refusal.
