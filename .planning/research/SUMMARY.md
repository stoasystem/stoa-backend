# v4.5 Research Summary: Support Evidence Integrations

**Updated:** 2026-06-12
**Milestone:** v4.5 Support Evidence Integrations And Operations Handoff

## Research Sources

- Existing backend code: `src/stoa/services/support_handoff_service.py`, `src/stoa/db/repositories/report_repo.py`, and `tests/test_admin_report_ops.py`.
- Existing planning history: v2.4/v2.5 support handoff milestone artifacts and v4.4 remaining-work audit.
- Zendesk ticket API docs: https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- Freshdesk API docs: https://developers.freshdesk.com/api/
- Help Scout create conversation docs: https://developer.helpscout.com/mailbox-api/endpoints/conversations/create/
- Amazon SES raw email docs: https://docs.aws.amazon.com/ses/latest/dg/send-email-raw.html

## Main Findings

- STOA already has the correct safety baseline: metadata-only support handoff packages, manual preview/copy/download modes, append-only audit rows, and explicit refusal for unapproved external writes.
- v4.5 should not start by choosing a CRM vendor. It should first define approved destination modes, credential readiness, provider-neutral payload shape, idempotency, lifecycle status, and refusal semantics.
- Zendesk, Freshdesk, Help Scout, and SES/shared mailbox all require provider-specific field mapping and credential setup. This argues for an adapter seam and fail-closed readiness checks.
- Operator value comes from delivery status, queue visibility, retry/refusal evidence, and clear fallback behavior, not from broad two-way ticket synchronization.
- Attachments are high-risk. If v4.5 includes attachments at all, they should be limited to generated redacted package JSON/markdown and protected by size/type limits.

## Recommended v4.5 Shape

1. Phase 148: define destination contract and credential readiness, including approved modes and refusal behavior.
2. Phase 149: implement a narrow delivery service and one approved destination path, preserving manual fallback.
3. Phase 150: add operator handoff queue/status visibility and retry/refusal evidence.
4. Phase 151: verify redaction, refusal, delivery state, credential readiness, and update remaining-feature docs.

## Decision

Use v4.5 to bridge the existing support-safe package workflow into controlled operations handoff. Keep the existing privacy model intact and treat every unapproved or unconfigured external write as refused until the selected destination has explicit credentials, payload mapping, idempotency, and audit coverage.
