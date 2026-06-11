# v4.5 Feature Research: Support Evidence Integrations

**Updated:** 2026-06-12
**Milestone:** v4.5 Support Evidence Integrations And Operations Handoff

## Feature Thesis

STOA already creates support-safe handoff packages. The missing product capability is controlled operational delivery: approved destinations, credential readiness, delivery lifecycle state, and operator-visible status without weakening metadata-only privacy boundaries.

## Table Stakes

| Capability | Priority | Notes |
|------------|----------|-------|
| Destination contract | P0 | Define exact destination modes, payload shape, required fields, credentials, refusal behavior, and audit metadata before any live write. |
| Credential/config readiness | P0 | Operators need to know whether a destination is configured and approved without exposing secrets. |
| Fail-closed delivery service | P0 | Unknown, unconfigured, or unapproved destinations must be refused before evidence reads or provider calls. |
| Existing fallback preservation | P0 | `preview`, `copy`, and `download` remain available even when external delivery is unavailable. |
| Delivery status lifecycle | P0 | Track `created`, `queued`, `sent`, `failed`, `refused`, and `retried` states. |
| Provider object references | P1 | Store ticket/conversation/message IDs and URLs only after validation and redaction. |
| Operator queue/list/detail | P1 | Admins need recent handoff status, filters, detail views, and retry/refusal evidence. |
| Idempotency/deduplication | P1 | Avoid duplicate tickets or emails for the same package/destination/request. |
| Attachment policy | P2 | Keep disabled or restricted to redacted JSON/markdown package artifacts; never attach raw report artifacts. |
| Multi-provider expansion | P2 | Provider adapters should be extensible, but v4.5 should prove one approved path first. |

## Candidate Destination Modes

- `internal_queue`: stores a handoff delivery record for operator triage without third-party writes.
- `shared_mailbox`: sends a redacted handoff email through an approved SES/shared-mailbox path.
- `zendesk_ticket`: creates a ticket through Zendesk after account/domain/token/field mapping is approved.
- `freshdesk_ticket`: creates a Freshdesk ticket after domain/API-key/field mapping is approved.
- `helpscout_conversation`: creates a Help Scout conversation after mailbox/customer/thread mapping is approved.

## User Stories

- As an admin, I can see which support destinations are approved and configured before I attempt delivery.
- As an admin, I can send a support-safe package to one approved destination and receive a clear sent, failed, or refused result.
- As an admin, I can fall back to preview/copy/download if external delivery is not configured.
- As an operator, I can filter recent handoffs by status, destination, package ID, and failure/refusal reason.
- As an implementer, I can add a provider adapter without bypassing redaction, metadata-only payload rules, or audit logging.

## Exclusions

- Two-way CRM synchronization.
- Automated customer messaging campaigns.
- Broad SLA analytics.
- Direct raw report artifact links, private S3 keys, presigned URLs, or unredacted provider/customer payloads.
- Credential setup inside the admin UI.

## Feature Decision

Build v4.5 as a narrow support-operations bridge, not a CRM platform. Phase 148 should define the exact contract; Phase 149 should add one credential-gated delivery path; Phase 150 should make delivery status visible and operable.
