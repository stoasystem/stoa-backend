# v4.5 Stack Research: Support Evidence Integrations

**Updated:** 2026-06-12
**Milestone:** v4.5 Support Evidence Integrations And Operations Handoff

## Current STOA Stack

- Backend: FastAPI/Python services under `src/stoa`.
- Persistence: existing report/audit DynamoDB repository helpers in `src/stoa/db/repositories/report_repo.py`.
- Existing support handoff: `src/stoa/services/support_handoff_service.py` generates metadata-only packages for `preview`, `copy`, and `download`, and refuses `external_write`.
- Existing tests: `tests/test_admin_report_ops.py` covers admin-only support handoff generation, redaction, missing references, failed release evidence, and external-write refusal.
- Existing privacy boundary: support packages compose sanitized recovery, release, fixture, and operator-note sections without raw report artifacts, presigned URLs, auth tokens, or broad customer payloads.

## External Destination Research

| Destination | Official source | Relevant shape | v4.5 implication |
|-------------|-----------------|----------------|------------------|
| Zendesk tickets | https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/ | Ticket creation uses `/api/v2/tickets` with subject/comment/requester/tags/custom fields; attachments use a separate upload flow. | Treat as an adapter behind an allowlisted credential path; keep attachments disabled until explicitly approved and size-limited. |
| Freshdesk tickets | https://developers.freshdesk.com/api/ | The v2 API exposes `POST /api/v2/tickets`, supports ticket fields, attachments, and rate limits. | Requires per-domain credential config, rate-limit handling, and provider field mapping. |
| Help Scout conversations | https://developer.helpscout.com/mailbox-api/endpoints/conversations/create/ | Create conversation requires `subject`, `mailboxId`, `customer`, and at least one `threads` entry; tags and custom fields are optional. | Good support-desk target, but it needs mailbox and customer mapping, so start contract-first. |
| Shared mailbox via SES | https://docs.aws.amazon.com/ses/latest/dg/send-email-raw.html | SES raw email uses `SendEmail` with raw content; MIME enables text/html parts and attachments, with attachment content base64 encoded. | Lowest operational dependency if SES is already approved, but still needs verified sender/recipient policy and MIME safety limits. |

## Recommended Runtime Shape

- Add no broad new dependency during Phase 148. Use existing Python HTTP/client patterns if present; otherwise introduce an adapter seam before selecting a concrete provider implementation.
- Model destinations as explicit modes, not a free-form URL:
  - `preview`
  - `copy`
  - `download`
  - `internal_queue`
  - `shared_mailbox`
  - `zendesk_ticket`
  - `freshdesk_ticket`
  - `helpscout_conversation`
- Keep all external destination modes fail-closed until an allowlisted environment/secret reference is present.
- Use a provider-independent delivery record with redacted request metadata, provider object ID, status, failure/refusal reason, retry count, and package reference.
- Prefer metadata-only package delivery. Attachments should stay off by default; if added later, they must be generated from the redacted package JSON/markdown only, not raw report artifacts.

## Credential Readiness

- Credentials must be referenced by named secret/env keys, not stored in planning docs or audit rows.
- Each destination needs an operator-visible readiness result:
  - configured/not configured
  - credential reference present/missing
  - destination allowlisted/refused
  - provider-specific required fields present/missing
  - dry-run/refusal-safe status
- Provider errors and rate-limit responses should be recorded as failed or retryable, not collapsed into generated package success.

## Fit Decision

v4.5 should start with a destination contract and readiness layer, then implement one narrow approved delivery path. The existing `external_write` refusal is a correct safety default and should remain until the selected destination has credentials, payload mapping, idempotency, and audit behavior defined.
