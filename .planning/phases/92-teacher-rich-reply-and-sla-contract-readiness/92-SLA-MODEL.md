# SLA Model: Teacher Takeover

**Phase:** 92
**Status:** Planned

## Event Timestamps

Required where data exists:

- `teacher_requested_at`
- `queue_visible_at`
- `teacher_taken_over_at`
- `teacher_first_replied_at`
- `resolved_at`

## Metrics

- Request to takeover duration.
- Request to first reply duration.
- Takeover to first reply duration.
- Request to resolved duration.
- SLA bucket: `within_target`, `at_risk`, `breached`, `unknown`.

## Reporting

Teacher queue/session UI may show per-question SLA state. Admin stats should expose aggregate SLA metrics only. Aggregates must not include private question content.

## Open Decisions

- SLA target threshold for MVP operations.
- Whether compensation/reporting depends on first reply, takeover, resolution, or all three.
- Whether unanswered queued requests need automatic requeue/escalation in a later milestone.
