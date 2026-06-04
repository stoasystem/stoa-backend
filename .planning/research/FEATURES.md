# Project Research - Features

**Milestone:** v1.4 Report Operations Admin UI / Bulk Recovery
**Date:** 2026-06-04

## Feature Categories

### Admin Report Operations List

Table stakes:

- Admin can open a report operations page from admin navigation.
- Admin can see report rows with parent, student, week, report status, email status, generation error class, delivery error class, last operation, and updated time.
- Admin can filter by status family: generated/sent, `email_failed`, `generation_failed`, pending/in-progress, and all.
- Admin can filter by week start and parent/student identifiers where backend supports it.
- Admin can page through results using opaque continuation tokens.
- Empty, loading, error, and stale-data states are explicit.

Differentiators:

- Summary counters for failed generation, failed email, sent, and stale/in-progress reports.
- Quick links from dashboard to failed report queues.
- Human-readable operation result badges.

### Report Operation Detail

Table stakes:

- Admin can inspect one report's metadata without using AWS Console.
- Detail shows artifact key metadata, generation error metadata, delivery error metadata, and operation audit fields.
- Detail never shows raw HTML/JSON content, public S3 URLs, presigned URLs, or direct S3 fetch controls.
- Detail exposes allowed actions based on current status.

Differentiators:

- Timeline-like operation history if existing record fields are enough.
- Inline reason why an action is disabled.

### Single `generation_failed` Retry

Table stakes:

- Admin can retry one report in `generation_failed`.
- Retry targets one `(parent_id, student_id, week_start)` only.
- Retry regenerates report content, writes JSON/HTML artifacts, writes metadata, and attempts email delivery through existing report service behavior.
- Retry refuses already successful reports and does not regenerate unrelated reports.
- Retry records attempted/completed/failed fields, actor, result, and error class/message.

Differentiators:

- Show before/after status in the response.
- Expose retry as a detail action before adding it to bulk flows.

### Selected Bulk Resend

Table stakes:

- Admin can select multiple `email_failed` report rows and request resend.
- Backend enforces max batch size.
- Backend returns per-report results: success, refused, not found, or failed with error class/message.
- Successful resend updates the report to `email_sent`/`sent`; failed resend preserves failed state and records audit fields.
- UI shows per-row operation progress and result after the batch.

Differentiators:

- Filter "email_failed this week" and select all visible rows.
- Confirmation dialog summarizing count and risk before sending.

### Operational Safety and Verification

Table stakes:

- All report ops endpoints remain admin-only.
- Backend validates every selected report identifier and status before action.
- Repeated retry/resend attempts are idempotent enough to avoid duplicate successful report metadata or accidental regeneration of successful reports.
- Backend and frontend tests cover permissions, filters, action eligibility, bulk results, and privacy constraints.
- Live verification confirms deployed API and frontend behavior after implementation.

Deferred:

- Full cross-system incident management.
- Rich historical audit log beyond report record fields.
- PDF/multilanguage report expansion.
- Billing-gated report operations.
- Step Functions-based orchestration.
