# Governance Contract: Retention Policy And Legal Hold Operations

**Phase:** 83
**Status:** Planned

## Scope

This contract governs approval and operation of immutable evidence retention and legal-hold workflows for report operations metadata-only evidence. It does not provide legal advice and does not claim compliance unless approval evidence is recorded.

## Roles

- `policy_owner`: accountable for retention policy version and periodic review.
- `legal_compliance_approver`: accountable for approving retention period and legal-hold operating procedure.
- `admin_operator`: executes approved metadata-only actions through admin APIs/UI.
- `auditor`: reviews approval evidence, hold state, and release evidence.
- `break_glass_approver`: authorizes emergency exceptions when documented policy allows them.

## Approval States

- `not_requested`
- `pending_review`
- `approved`
- `changes_requested`
- `rejected`
- `expired`
- `superseded`

Approval records must include policy version, retention mode, retention days, owner, approver metadata, evidence references, decision timestamp, decision reason, next review due date, and source request ID.

## Review Cadence

The initial review cadence must be defined before recording an approved policy. Review records should include due date, reviewer, outcome, next due date, and append-only audit evidence.

## Break-Glass Policy

Break-glass behavior must be documented before backend/UI actions rely on it. Required fields include reason, approver, allowed action, time window, affected scope, evidence references, and post-event review requirement. Break-glass must not silently bypass privacy validation or delete immutable evidence.

## Privacy Boundary

Governance records may contain metadata and redacted evidence references only. They must not include raw report artifacts, S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, cookies, passwords, AWS secrets, or private storage identifiers.

## Compliance Language

Allowed language: "technical Object Lock behavior verified" and "retention policy approved" only when the corresponding evidence exists.

Forbidden language: broad regulatory compliance claims without formal legal/compliance approval evidence.
