# Phase 161 Support Provider Expansion Contract

## Scope

v4.8 extends the v4.5 support handoff foundation from `internal_queue` into approved provider-backed support operations. The implementation target is a provider adapter layer that can create support tickets from existing support-safe evidence packages, retry failed deliveries, synchronize provider ticket state, compute support SLA analytics, and send controlled support/customer messages from approved templates.

## Destination Modes

| Mode | Purpose | Write Allowed | Credential State |
|------|---------|---------------|------------------|
| `internal_queue` | Existing STOA-managed queue fallback | Yes when approved | `none_required` |
| `third_party_support` | Approved provider ticket creation | Only when destination and credentials are approved | `missing`, `configured`, `verified`, `failed` |
| `crm_message` | Controlled customer/support messaging | Only through approved templates and destinations | `missing`, `configured`, `verified`, `failed` |
| `disabled` | Explicitly block external writes | No | `not_applicable` |

Unapproved modes must return a refusal with an actionable blocker reason and no external write.

## Support-Safe Payload Boundary

Allowed provider payload fields:

- Support package ID, support ticket ID, report operation IDs, recovery job IDs, fixture/release evidence IDs, and audit IDs.
- Public or operator-safe status values, timestamps, lifecycle states, counts, retry eligibility, and redacted error categories.
- Parent/student/operator identifiers only in the same bounded form already allowed by support-safe evidence packages.
- Operator notes that have passed existing support handoff validation.

Disallowed fields:

- Raw report JSON/HTML, S3 keys under `weekly-reports/`, presigned URLs, raw S3 object bodies, auth tokens, raw provider payloads, payment secrets, and unredacted private customer content.

## Ticket Lifecycle

Canonical STOA states:

- `queued`
- `delivery_pending`
- `delivered`
- `delivery_failed`
- `retry_pending`
- `acknowledged`
- `in_progress`
- `waiting_on_customer`
- `resolved`
- `reopened`
- `sync_conflict`
- `cancelled`

Provider-specific states must map into this vocabulary while retaining a redacted provider status label for operator visibility.

## Idempotency And Correlation

- Provider ticket creation uses a deterministic idempotency key derived from destination, support package ID, target provider, and ticket purpose.
- Provider ticket rows store `provider_ticket_id`, `provider_ticket_url` when safe, `provider_status`, `provider_updated_at`, `last_synced_at`, `attempt_count`, and redacted `last_error_code`.
- Duplicate create attempts must return the existing delivery record when the idempotency key matches.
- Conflicting provider IDs for the same idempotency key must be surfaced as `sync_conflict`.

## Retry Contract

- Retry eligibility applies only to `delivery_failed` and `retry_pending` states with remaining attempts.
- Retry workers persist attempt count, next eligible time, last attempt time, and redacted failure category.
- Exhausted retries become operator-visible `delivery_failed` records with `retry_exhausted=true`.
- Retry must not create duplicate tickets when a previous provider call succeeded but the local response was interrupted.

## Two-Way Sync Contract

Sync sources may be provider webhooks or polling-shaped adapters. Both must normalize into the same internal update command.

Rules:

- Ignore duplicate provider events by provider event ID or provider updated timestamp.
- Refuse stale updates older than the current `provider_updated_at`.
- Preserve local terminal states unless the provider update is explicitly newer and maps to `reopened`.
- Mark conflicts when provider state cannot be mapped or contradicts a local terminal transition.
- Store sync freshness and redacted conflict reason for admin visibility.

## SLA Analytics Contract

SLA inputs:

- Time from package creation to queue.
- Time from queue to provider delivery.
- Time from delivery to provider acknowledgement.
- Time from acknowledgement to first provider response.
- Time from first response to resolution.
- Failure and retry backlog counts.
- Reopen counts and unresolved age.

Admin analytics should expose aggregate counts, p50/p95 durations where enough data exists, overdue buckets, provider failure rates, retry backlog, and message delivery outcomes.

## Controlled CRM/Customer Messaging

Allowed template categories:

- Support receipt confirmation.
- Support status update.
- Resolution notice.
- Escalation notice.

Message sends require:

- Approved destination mode.
- Approved template ID and locale.
- Support ticket correlation.
- Opt-out or no-contact check when available.
- Persisted send/refusal/failure evidence.

Broad marketing campaigns, freeform CRM blasts, and unrelated lifecycle messaging are out of scope.

## Implementation Handoff

Phase 162 should implement adapter readiness and provider ticket delivery.

Phase 163 should implement retry workers and two-way sync.

Phase 164 should implement SLA analytics and controlled messaging.

Phase 165 should verify the full support-provider release gate and record whether the provider state is `internal-only`, `provider-ready`, `provider-enabled`, `blocked`, or `deferred`.
