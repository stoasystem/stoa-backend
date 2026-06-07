# Legal Hold And Retention Policy Contract

**Phase:** 75
**Status:** Planned

## Scope

Legal hold and retention policy metadata apply to supported report operations audit evidence scopes. They do not delete audit rows, rewrite existing evidence, expose private artifacts, or bypass immutable storage privacy validation.

## Policy Metadata

Required policy fields:

- `policy_id`
- `policy_name`
- `retention_category`
- `retention_clock_start`
- `minimum_retention_until`
- `created_by`
- `created_at`
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

## Privacy Boundary

Legal hold and policy APIs may return only allowlisted metadata. Responses must not include raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, or AWS secrets.

## Operator Visibility

Admin UI should show policy ID/name, hold state, timestamps, actor metadata, refusal reasons, and digest/reference metadata. It should not show storage internals or private object paths.
