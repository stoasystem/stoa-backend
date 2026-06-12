---
gsd_state_version: 1.0
milestone: v4.8
milestone_name: Support Provider Expansion And CRM Automation
status: Planned
last_updated: "2026-06-12T12:30:18.440Z"
last_activity: 2026-06-12
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 5
  completed_plans: 2
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.8 support provider expansion and CRM automation.

## Current Position

Phase: 163 - Retry Workers And Two-Way Ticket Synchronization
Plan: Not started
Status: Planned
Last activity: 2026-06-12

## Accumulated Context

### Decisions

- v4.5 completed support evidence integration through the controlled `internal_queue` path, leaving third-party support provider adapters, retry workers, two-way sync, SLA analytics, and broader CRM/customer messaging as future scope.
- v4.6 completed curriculum authoring and analytics foundation.
- v4.7 completed payment production activation automation with final live activation status `deferred` because external provider prerequisites remain outstanding.
- `stoa_docs` remaining feature queue now recommends support provider expansion and CRM automation as the next direct product/operations build.
- v4.8 should prioritize functional support provider integration, provider delivery workers, retry and synchronization, SLA analytics, and controlled support messaging.
- Support evidence boundaries remain metadata-only. External support/CRM destinations must be explicitly approved before writes are enabled.
- Internal development mode means verification should stay focused on feature behavior, idempotency, refusal paths, and operator-visible state rather than broad security/compliance sweeps.

### Pending Todos

- Add retry worker and two-way ticket synchronization in Phase 163.
- Add support SLA analytics and controlled CRM/customer messaging in Phase 164.
- Close v4.8 with release-gate evidence and next milestone selection in Phase 165.

### Blockers/Concerns

- Third-party support provider selection and credentials may remain external dependencies.
- CRM/customer messaging requires approved templates, destination policy, and operator visibility before sending.
- Existing metadata-only support evidence boundaries must continue to block raw report artifacts, presigned URLs, raw report JSON/HTML, auth tokens, and raw provider payloads.

## Operator Next Steps

- Start Phase 163 after context and planning for retry workers and two-way ticket synchronization.
