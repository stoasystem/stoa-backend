# Phase 71 Audit Retention Contract

**Status:** Complete
**Created:** 2026-06-07

## Purpose

Define how audit evidence can be represented for stronger retention without storing raw private report artifacts or claiming compliance-grade immutability prematurely.

## Audit Classes

Supported classes for v2.6 manifests:

- Report recovery operations.
- Recovery jobs and targets.
- Generation retry and resend actions.
- Report edit and artifact edit actions.
- Artifact rollback actions.
- Release evidence validation and safe-fixture status checks.
- Support handoff package generation/refusal.

Initial Phase 72 allowlist:

| Scope | Reference | Source rows | Notes |
|-------|-----------|-------------|-------|
| `recovery_job` | `job_id` | Recovery job summary, target snapshots, recovery job audit rows | Primary scope for manifest generation/status. |
| `report` | `parent_id`, `student_id`, `week_start` | Report summary metadata and report audit rows | No artifact object reads; only summary/audit metadata already available through admin report operations. |
| `support_handoff` | `package_id` | Support handoff audit rows | Status only until repository list support exists; no external destination writes. |
| `release_evidence` | Inline release evidence bundle | Release evidence validation output | Ephemeral validation input; manifest stores only sanitized validation metadata. |

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

## Item Digest Rules

- Compute per-item digests from canonical JSON summaries after sanitization and stable key ordering.
- Compute the manifest digest from the sanitized manifest body excluding transient download/copy presentation fields.
- Store counts, item refs, item digests, and manifest digest; do not store raw audit payloads or artifact bodies.
- Treat missing references as `partial` when at least one supported item is included, and `refused` when no supported item can be included.

## Persistence Decision

Phase 72 supports both:

- Ephemeral preview/download response returned to the admin.
- Redacted append-only audit metadata recording manifest generation or refusal.

Phase 72 does not need to persist the full manifest body as a durable object. Full persisted immutable evidence remains future scope until a CDK-managed immutable storage path exists.

## Status Values

| Status | Meaning |
|--------|---------|
| `sealed` | Manifest generated from supported metadata-only evidence and has stable digest metadata. |
| `unsealed` | Supported scope exists but no manifest generation has been recorded in current response context. |
| `partial` | Some requested references were missing/skipped but at least one supported item was included. |
| `refused` | Request asked for destructive retention, WORM mutation, unsupported privacy content, or no supported refs. |
| `unsupported` | Scope exists in future roadmap but is not supported by v2.6 APIs. |

## Privacy Boundary

Retention manifests must not include:

- S3 keys or bucket/object paths for private report artifacts.
- Presigned URLs.
- Raw report JSON or HTML.
- Raw artifact payloads.
- Auth tokens, passwords, cookies, AWS keys, or session secrets.

Also avoid private storage identifiers in committed verification evidence and frontend-rendered output. Artifact version IDs and report IDs are allowed because existing report operations already expose them as metadata-only operational references.

## Phase 72 Constraints

- Generate bounded manifests from explicit references and recent recovery-job metadata.
- Prefer hashes of canonical metadata summaries over raw payload storage.
- Refuse destructive retention operations.
- Record redacted audit metadata for manifest generation/refusal.
- Reuse `release_evidence_service.private_marker_hits` and existing recovery-evidence sanitizers for privacy checks.
