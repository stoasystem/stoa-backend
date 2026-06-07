# Legal Hold And Retention Policy Contract

**Phase:** 75
**Status:** Complete

## Scope

Legal hold and retention policy metadata apply to supported report operations audit evidence scopes. They do not delete audit rows, rewrite existing evidence, expose private artifacts, or bypass immutable storage privacy validation.

## Policy Metadata

Required policy fields:

- `policy_id`
- `policy_name`
- `retention_category`
- `retention_clock_start`
- `minimum_retention_until`
- `applies_to_scope_types`
- `default_action`
- `created_by`
- `created_at`
- `updated_by`
- `updated_at`
- `status`

Policy metadata must be backend-owned and audit logged. Manual AWS console policy edits are out of scope.

## Legal Hold States

Supported states:

- `none`
- `active`
- `release_requested`
- `released`
- `refused`

Required hold fields:

- `hold_id`
- `scope_type`
- `scope_id`
- `state`
- `reason`
- `created_by`
- `created_at`
- `updated_by`
- `updated_at`
- `source_request_id`

## State Change Rules

- Applying a hold requires admin authorization and a non-empty operator reason.
- Releasing a hold requires admin authorization and a non-empty release reason.
- Unsupported scopes are refused.
- Destructive retention actions are refused.
- Every hold state change writes append-only audit metadata.
- Prior audit rows and immutable evidence references are not deleted or overwritten.
- Hold state changes must use compare-and-set semantics against the current hold metadata version when a hold already exists.
- Releasing a hold changes metadata state only; it does not delete retained evidence or shorten an already-enforced retention clock.

## Backend Integration Contract

Phase 76 should model legal hold records separately from immutable evidence object payloads:

- `LEGAL_HOLD#{hold_id}` or equivalent metadata row for current hold state.
- Append-only audit event for each apply/release/refusal.
- Optional immutable evidence reference list by scope and digest.
- Admin-only read/status APIs that return allowlisted policy and hold metadata.

The first implementation should support report operations evidence scopes already covered by v2.6 retention manifests: recovery jobs, report audit refs, release evidence refs, support handoff refs, and retention manifests. Unsupported scopes must return a refusal rather than falling back to generic storage.

## Privacy Boundary

Legal hold and policy APIs may return only allowlisted metadata. Responses must not include raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, or AWS secrets.

## Operator Visibility

Admin UI should show policy ID/name, hold state, timestamps, actor metadata, refusal reasons, and digest/reference metadata. It should not show storage internals or private object paths.

State-changing UI actions must be separated from read-only status and require explicit operator reason fields.
