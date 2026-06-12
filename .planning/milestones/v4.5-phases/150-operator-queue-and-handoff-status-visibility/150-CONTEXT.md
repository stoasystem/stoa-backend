# Phase 150 Context: Operator Queue And Handoff Status Visibility

**Created:** 2026-06-12  
**Mode:** autonomous smart discussion  
**Requirement:** SUPPORTINT-03

## Phase Goal

Give operators bounded admin visibility into support handoff delivery status, recent activity, failure/refusal reasons, and retry state.

## Locked Inputs From Prior Phases

- Phase 148 selected `internal_queue` as the first approved support destination path.
- Phase 149 implemented `POST /admin/reports/support-handoff-delivery`.
- Phase 149 stores provider-neutral delivery summary rows under `SUPPORT_HANDOFF_DELIVERY#{delivery_id}` with `SK=SUMMARY`.
- Phase 149 stores append-only delivery audit rows under the same partition with `SK=AUDIT#...`.
- Existing package audit rows remain separate under `SUPPORT_HANDOFF#{package_id}`.
- `queued` is the successful `internal_queue` intake state.
- `refused` is used for missing approval, contract-defined unapproved destinations, and package privacy/validation failures.
- Unknown destinations remain `422` before evidence reads.
- Third-party destinations remain refused until later provider phases.

## Phase 150 Success Criteria

1. Admin-only list/detail APIs expose recent support handoff records with bounded filters for status, destination, package ID, and date range.
2. Operators can distinguish created, queued, sent, failed, refused, and retried handoffs with provider references where available.
3. Retry behavior is explicit, bounded, idempotent, and unavailable for privacy-failed or unapproved destinations.
4. Queue/status outputs do not expose raw report artifacts, secrets, authorization headers, presigned URLs, or unredacted outbound payloads.

## Implementation Direction

- Add repository helpers for listing recent support handoff delivery summaries and reading one delivery detail with bounded audit events.
- Add admin-only queue/list and detail endpoints under the existing admin report operations router.
- Keep returned payloads metadata-only: delivery fields, package ID, destination mode, status, actor, timestamps, correlation ID, retry count, retryable flag, provider object reference, redacted reasons, privacy result, evidence reference IDs, payload digest, and bounded audit event metadata.
- Do not expose raw package sections, raw delivery payload, raw provider payload, raw report artifacts, S3 keys, presigned URLs, cookies, authorization headers, API keys, or OAuth tokens.
- Retry in Phase 150 should be explicit but bounded. If implementation includes a retry endpoint, it must only be available for retryable queued/failed internal queue records and must refuse privacy-failed or unapproved destinations. If safe retry cannot be implemented without broad mutation semantics, expose retry eligibility and defer mutation to a future phase.

## Candidate Endpoints

- `GET /admin/reports/support-handoff-deliveries`
- `GET /admin/reports/support-handoff-deliveries/{delivery_id}`
- Optional bounded retry path if safe: `POST /admin/reports/support-handoff-deliveries/{delivery_id}/retry`

## Validation Expectations

- Non-admin queue/detail access returns 403 without table queries.
- List filters are bounded by limit and supported statuses/destinations.
- Detail returns bounded audit events and does not expose raw payloads.
- Retry eligibility is visible and privacy/unapproved/refused records are not retryable.
- Existing support handoff delivery and package tests remain green.

## Files To Read During Research

- `.planning/phases/149-support-evidence-export-destination-integration/149-01-SUMMARY.md`
- `.planning/phases/149-support-evidence-export-destination-integration/149-VERIFICATION.md`
- `src/stoa/services/support_destination_service.py`
- `src/stoa/db/repositories/report_repo.py`
- `src/stoa/routers/admin.py`
- `tests/test_admin_report_ops.py`
