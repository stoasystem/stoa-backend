# Immutable Audit Storage Contract

**Phase:** 75
**Status:** Planned

## Scope

The immutable audit storage object is a metadata-only persistence form of v2.6 retention manifests. It is designed to make report operations audit evidence durable, verifiable, and retention-aware without storing private report payloads.

## Object Identity

Required identity fields:

- `scope_type`: supported audit scope such as `report_operation`, `recovery_job`, `release_evidence`, `support_handoff`, or `retention_manifest`.
- `scope_id`: stable backend identifier for the selected scope.
- `manifest_version`: schema version.
- `canonical_digest`: digest of the canonical metadata-only manifest.
- `created_at`: UTC timestamp.
- `created_by`: admin actor identifier.
- `source_request_id`: API request ID that created the object.
- `policy_id`: retention policy identifier.

Object identity must not include raw report artifact paths, S3 keys, presigned URLs, raw report JSON, raw report HTML, auth tokens, cookies, passwords, or AWS secrets.

## Payload

Allowed payload categories:

- Audit event type and stable event identifiers.
- Report operation IDs, recovery job IDs, release evidence IDs, support handoff IDs, and retention manifest IDs.
- Timestamps, actor IDs, action names, status values, refusal reasons, and redacted validation findings.
- Canonical digest metadata and verification algorithm names.
- Retention category, retention clock, policy ID, legal hold state, and hold reason metadata.

Forbidden payload categories:

- Raw report artifacts.
- S3 keys or bucket/key pairs.
- Presigned URLs.
- Raw report JSON or HTML.
- Auth tokens, cookies, passwords, AWS access keys, AWS secret keys, or session tokens.
- Raw unreviewed evidence bundles.

## Status Model

Supported immutable evidence statuses:

- `not_configured`: immutable storage is not available.
- `ready`: CDK-managed immutable storage is configured.
- `persisted`: metadata-only manifest persisted successfully.
- `refused`: request failed a policy, authorization, scope, or privacy gate.
- `verification_failed`: stored digest or metadata verification failed.
- `legal_hold_active`: evidence is under legal hold.

## Failure Behavior

Backend write paths must fail closed when:

- Immutable storage environment configuration is missing.
- CDK readiness has not been recorded.
- Payload validation finds forbidden private markers.
- Scope is unsupported.
- Actor is not admin.
- Required retention policy metadata is missing.

## Release Evidence

Release evidence must record the CDK source path, deploy run ID, commit SHA, environment variables, API request IDs, redacted request/response samples, and privacy denylist results before v2.7 can claim immutable storage support.
