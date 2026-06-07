# Backend Configuration Contract: Immutable Evidence Storage

**Phase:** 79
**Status:** Complete

## Runtime Settings

Phase 80/81 must use these exact backend settings:

- `IMMUTABLE_AUDIT_STORAGE_MODE=cdk_managed`
- `IMMUTABLE_AUDIT_STORAGE_CDK_MANAGED=true`
- `IMMUTABLE_AUDIT_STORAGE_RESOURCE=stoa-immutable-evidence-{account}`
- `IMMUTABLE_AUDIT_STORAGE_PREFIX=audit-retention/`

Settings must be injected by CDK. Local defaults must keep immutable persistence disabled unless explicitly configured for tests.

## Status Transitions

Expected runtime states:

- `not_configured`: no CDK-injected immutable storage settings.
- `ready`: immutable storage settings are present and validated by `report_audit_retention_service._immutable_storage_status()`.
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

## Configured Persistence Behavior

When settings are injected and `_immutable_storage_status()` returns `ready`, `persist_immutable_manifest()` must:

1. Build the canonical metadata-only manifest.
2. Insert a DynamoDB manifest reference with `status=pending_object_write`.
3. Write the immutable object to `audit-retention/{immutable_ref_id}.json` using create-only S3 semantics.
4. Record byte-level object digest and key digest metadata.
5. Transition the DynamoDB reference to `status=persisted`.
6. Write append-only audit metadata.

If the object write fails, the DynamoDB reference must transition to `refused`. If the final transition fails after object write, the pending reference remains as reconciliation evidence.

## API Privacy Boundary

API responses may expose operator-safe immutable evidence references and digest metadata. They must not expose raw object payloads, report artifact S3 keys, presigned URLs, raw JSON/HTML, tokens, cookies, passwords, or AWS secrets.
