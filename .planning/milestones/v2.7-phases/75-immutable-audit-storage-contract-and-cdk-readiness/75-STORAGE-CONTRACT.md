# Immutable Audit Storage Contract

**Phase:** 75
**Status:** Complete

## Scope

The immutable audit storage object is a metadata-only persistence form of v2.6 retention manifests. It is designed to make report operations audit evidence durable, verifiable, and retention-aware without storing private report payloads.

## Object Identity

Required identity fields:

- `immutable_ref_id`: stable backend reference ID for the persisted immutable evidence record.
- `scope_type`: supported audit scope such as `report_operation`, `recovery_job`, `release_evidence`, `support_handoff`, or `retention_manifest`.
- `scope_id`: stable backend identifier for the selected scope.
- `manifest_version`: schema version.
- `canonical_digest`: digest of the canonical metadata-only manifest.
- `digest_algorithm`: digest algorithm, initially `sha256`.
- `created_at`: UTC timestamp.
- `created_by`: admin actor identifier.
- `source_request_id`: API request ID that created the object.
- `policy_id`: retention policy identifier.
- `retention_until`: UTC timestamp derived from the active policy, or null when no retention clock applies.
- `legal_hold_state`: current legal hold state at write time.

Object identity must not include raw report artifact paths, S3 keys, presigned URLs, raw report JSON, raw report HTML, auth tokens, cookies, passwords, or AWS secrets.

## Payload

Allowed payload categories:

- Audit event type and stable event identifiers.
- Report operation IDs, recovery job IDs, release evidence IDs, support handoff IDs, and retention manifest IDs.
- Timestamps, actor IDs, action names, status values, refusal reasons, and redacted validation findings.
- Canonical digest metadata and verification algorithm names.
- Retention category, retention clock, policy ID, legal hold state, and hold reason metadata.
- Storage write status, refusal status, verification timestamps, and redacted privacy validation findings.

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

Status responses may expose `immutable_ref_id`, digest metadata, policy metadata, status, timestamps, and redacted refusal reasons. They must not expose bucket names, object keys, presigned URLs, or raw object payloads to the frontend.

## Failure Behavior

Backend write paths must fail closed when:

- Immutable storage environment configuration is missing, incomplete, or not marked CDK-managed.
- CDK readiness has not been recorded in Phase 75/76 release evidence.
- Payload validation finds forbidden private markers.
- Scope is unsupported.
- Actor is not admin.
- Required retention policy metadata is missing.
- The requested action would overwrite or delete an existing immutable evidence object.

Failed writes must return operator-safe refusal metadata and write only redacted append-only audit metadata when the existing audit-retention audit path is available.

## Backend Integration Contract

Phase 76 should add a backend service boundary that:

- Builds the existing v2.6 canonical metadata-only retention manifest first.
- Validates the manifest against the existing private marker denylist before persistence.
- Resolves immutable storage configuration from CDK-managed environment variables.
- Writes the manifest only to the approved immutable evidence resource or prefix.
- Persists an append-only DynamoDB metadata reference containing `immutable_ref_id`, scope, digest, status, policy metadata, actor, and request ID.
- Exposes admin-only status/read APIs that return metadata references, not raw immutable object payloads or storage internals.

The existing DynamoDB audit rows remain the operational audit timeline. The immutable object is a durable retention artifact derived from those rows, not a replacement for the application audit model.

## Release Evidence

Release evidence must record the CDK source path, deploy run ID, commit SHA, environment variables, API request IDs, redacted request/response samples, and privacy denylist results before v2.7 can claim immutable storage support.

Until that evidence exists, the product language must say "immutable storage not configured" or "immutable persistence disabled", not "compliance-grade WORM storage enabled".
