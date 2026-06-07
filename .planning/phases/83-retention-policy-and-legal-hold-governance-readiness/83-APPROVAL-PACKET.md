# Approval Packet: Immutable Evidence Retention Policy

**Phase:** 83
**Status:** Planned

## Purpose

The approval packet is the evidence bundle legal/compliance reviewers need before approving the immutable evidence retention period and legal-hold operating procedure.

## Required Fields

- `policy_version`
- `retention_mode`
- `retention_days`
- `policy_owner`
- `legal_compliance_approver`
- `approval_state`
- `approval_reason`
- `decision_timestamp`
- `next_review_due_at`
- `source_request_id`

## Required Evidence References

- v2.8 infra deploy run ID and commit SHA.
- v2.8 backend deploy run ID and commit SHA.
- CDK diff/deploy evidence.
- S3 Object Lock mode/days verification.
- Immutable manifest production smoke evidence.
- DynamoDB immutable metadata verification.
- Browser smoke and privacy denylist evidence.
- Residual risk statement.

## Reviewer Decision Options

- `approved`
- `changes_requested`
- `rejected`
- `expired`
- `superseded`

## Residual Risk Statement

The packet must say whether approval is pending or recorded. It must not imply that technical Object Lock verification is the same thing as legal/compliance approval.

## Forbidden Packet Content

- Raw report artifacts.
- S3 keys or private bucket/key pairs.
- Presigned URLs.
- Raw report JSON or HTML.
- Auth tokens, cookies, passwords, AWS access keys, AWS secret keys, or session tokens.
