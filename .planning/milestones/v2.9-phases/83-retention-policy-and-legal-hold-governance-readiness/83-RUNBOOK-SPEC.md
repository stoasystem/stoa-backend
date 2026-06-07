# Runbook Spec: Legal Hold Operations

**Phase:** 83
**Status:** Complete

## Operator Workflows

The runbook must cover:

- Inspect current retention policy approval status.
- Inspect active legal holds and review due dates.
- Apply a legal hold with owner, reason, scope, and review date.
- Release a legal hold with approver, reason, and evidence references.
- Record periodic legal-hold review.
- Refuse unsupported or destructive retention actions.
- Escalate incidents and emergency break-glass requests.
- Export metadata-only evidence for audit review.

## Required Operator Inputs

- Scope type and scope ID.
- Operator reason.
- Owner or reviewer.
- Review due date.
- Evidence references.
- Break-glass approval metadata when applicable.

## Safety Rules

- Legal-hold actions must be admin-only.
- State changes must be append-only audited.
- Destructive deletion must be refused.
- Raw artifacts and private storage identifiers must not be rendered or exported.
- Break-glass must be explicit, time-bounded, and reviewed after use.

## UI Expectations

Admin UI should separate read-only inspection from state-changing actions, require explicit reason fields, show refusal reasons, and surface review due dates without exposing private markers.
