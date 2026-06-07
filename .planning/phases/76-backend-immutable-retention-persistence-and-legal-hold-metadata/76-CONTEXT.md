# Phase 76: Backend Immutable Retention Persistence And Legal Hold Metadata - Context

**Gathered:** 2026-06-07
**Status:** Complete
**Mode:** Autonomous, derived from Phase 75 contracts

<domain>
## Phase Boundary

Phase 76 adds admin-only backend APIs and repository/service support for immutable evidence status, metadata-only immutable manifest persistence attempts, and legal hold metadata. Because Phase 75 found no CDK-managed immutable evidence resource or Lambda environment yet, production immutable object persistence must fail closed with operator-safe `not_configured` metadata until CDK evidence exists.

</domain>

<decisions>
## Implementation Decisions

### Immutable Persistence
- Reuse the v2.6 metadata-only audit retention manifest builder and privacy validation before any persistence attempt.
- Add a separate immutable evidence persistence status response instead of changing existing audit-retention manifest semantics.
- Persist only sanitized metadata references when immutable storage is configured; never return storage resource names, object keys, bucket names, presigned URLs, or raw manifest payloads.
- Return `not_configured` and write redacted audit metadata when CDK-managed immutable storage config is absent.

### Legal Hold Metadata
- Model legal hold as metadata state plus append-only legal-hold audit events.
- Support `apply` and `release` actions with required operator reasons.
- Reuse audit-retention references for report operations evidence scopes.
- Refuse unsupported scopes rather than falling back to generic storage.

### Privacy
- Continue using existing report recovery redaction, release evidence private marker detection, and audit-retention sanitization helpers.
- Keep all responses metadata-only and run private marker checks on composed responses.
- Preserve v2.6 refusal behavior for destructive retention actions.
- Do not expose raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, or AWS secrets.

### the agent's Discretion
All implementation choices not fixed above follow existing admin report operations service/router/test patterns.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/report_audit_retention_service.py` already builds metadata-only manifests, digests, privacy results, and redacted audit events.
- `src/stoa/routers/admin.py` already has admin-only audit retention schemas and endpoints.
- `src/stoa/db/repositories/report_repo.py` already has conditional append audit methods for report, recovery job, support handoff, and audit-retention events.
- `tests/test_admin_report_ops.py` already has focused audit retention endpoint tests and private marker assertions.

### Established Patterns
- Admin-only routes use `Depends(require_role("admin"))`.
- Request bodies use Pydantic models adjacent to related admin schemas.
- Repository append-only events use `ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)"`.
- Focused tests monkeypatch repository/service collaborators and assert no private artifact markers in responses/audit rows.

### Integration Points
- Add immutable/legal-hold endpoints beside `/admin/reports/audit-retention/*`.
- Add repository methods beside `put_audit_retention_audit_event`.
- Add settings for CDK-managed immutable storage gates in `src/stoa/config.py`.

</code_context>

<specifics>
## Specific Ideas

Use new endpoints rather than overloading `retention_action=legal_hold`, because v2.6 intentionally refuses `legal_hold`, `worm_write`, and `object_lock` actions on metadata-only manifests.

</specifics>

<deferred>
## Deferred Ideas

- Actual CDK immutable evidence storage resource and production object writes remain blocked until infra diff/deploy evidence exists.
- Frontend immutable evidence/legal hold controls are Phase 77.

</deferred>
