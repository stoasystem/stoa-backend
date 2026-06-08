# SLA Model: Teacher Takeover

**Phase:** 92
**Status:** Complete

## Event Timestamps

Required where data exists:

- `teacher_requested_at`
- `queue_visible_at`
- `teacher_taken_over_at` (`teacher_started_at` may remain as a backward-compatible alias)
- `teacher_first_replied_at`
- `resolved_at`
- `teacher_timeout_at` for future escalation/timeout automation; Phase 93 records the field only when a timeout path exists.

## Metrics

- Request to takeover duration.
- Request to first reply duration.
- Takeover to first reply duration.
- Request to resolved duration.
- SLA bucket: `within_target`, `at_risk`, `breached`, `unknown`.

MVP targets:

- First reply target: 30 minutes after `teacher_requested_at`.
- At-risk threshold: 20 minutes after `teacher_requested_at`.
- Takeover target: 15 minutes after `teacher_requested_at`.
- Unknown bucket applies when the source timestamp is absent or malformed.

## Reporting

Teacher queue/session UI may show per-question SLA state. Admin stats should expose aggregate SLA metrics only. Aggregates must not include private question content.

## Privacy Boundary

SLA stats may include counts, averages, maximum durations, and bucket counts. They must
not include question content, messages, student names, image keys, report artifact keys,
presigned URLs, auth tokens, cookies, passwords, or AWS secrets.

## CDK Readiness

No new CDK resource is required for the v3.1 MVP. SLA timestamps and rich reply metadata
can be stored on existing question/session DynamoDB rows. Admin aggregate scans already
exist for small-scale stats; future higher-volume GSI/indexing remains out of scope.

## Deferred Decisions

- Whether compensation/reporting depends on first reply, takeover, resolution, or all three.
- Whether unanswered queued requests need automatic requeue/escalation in a later milestone.
