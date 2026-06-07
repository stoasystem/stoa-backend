# Backend Configuration Contract: Immutable Evidence Storage

**Phase:** 79
**Status:** Planned

## Runtime Settings

Phase 79 must define exact backend settings for:

- Immutable evidence storage mode.
- Immutable evidence resource name.
- Immutable evidence object prefix or scope boundary.
- Digest/verification algorithm version.
- Retention policy identifier.
- Optional legal hold default behavior.

Settings must be injected by CDK. Local defaults must keep immutable persistence disabled unless explicitly configured for tests.

## Status Transitions

Expected runtime states:

- `not_configured`: no CDK-injected immutable storage settings.
- `configured`: immutable storage settings are present and validated.
- `persisted`: metadata-only manifest object write succeeded.
- `refused`: request failed auth, scope, config, idempotency, or privacy validation.
- `verification_failed`: object digest or metadata check failed.

## Failure Behavior

Backend must fail closed when:

- Configuration is missing or partial.
- IAM/object write fails.
- Duplicate create-only object identity conflicts unexpectedly.
- Privacy denylist finds forbidden markers.
- Actor is not admin.
- Scope is unsupported.

## API Privacy Boundary

API responses may expose operator-safe immutable evidence references and digest metadata. They must not expose raw object payloads, report artifact S3 keys, presigned URLs, raw JSON/HTML, tokens, cookies, passwords, or AWS secrets.
