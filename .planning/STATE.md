---
gsd_state_version: 1.0
milestone: v3.2
milestone_name: Content Moderation And Internal Operations
status: planning
last_updated: "2026-06-08T13:25:35+02:00"
last_activity: 2026-06-08
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 1
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.2 content moderation and internal operations.

## Current Position

Phase: 96 Content Moderation Contract And Data Model
Plan: 96-01
Status: Planned.
Last activity: 2026-06-08 - reviewed `stoa_docs` after v3.1 and selected the remaining MVP admin content moderation workflow for the next product-building milestone.

## Accumulated Context

### Decisions

- v1.8 shipped async generation retry jobs.
- v1.9 shipped recovery subset resume and support-safe evidence packages.
- v2.0 shipped controlled metadata-only report editing.
- Raw report artifact editing remains higher risk than metadata editing and must start with contract/CDK readiness before implementation.
- v2.1 must preserve backend-mediated artifact access and must not expose S3 keys, presigned URLs, raw JSON, or raw unreviewed HTML to frontend.
- v2.2 added artifact rollback and a named non-customer safe-fixture mutation verification path before broader artifact editing use.
- v2.3 should turn manually assembled release evidence into a repeatable redacted evidence workflow before expanding any production mutation capability.
- Direct external ticket writes must remain refused until an approved connector or secret-backed credential path exists.
- Compliance-grade WORM audit storage must not be claimed without deployed CDK-managed immutable storage evidence.
- v3.0 reconciled `stoa_docs` against the shipped backend/frontend state and closed account lifecycle, parent binding, OCR correction, quota hardening, and v2.9 production verification gaps.
- v3.1 closed teacher rich text/formula replies and response-time SLA tracking.
- v3.2 starts with content moderation because it is the only remaining visible MVP admin workflow in `stoa_docs`; this milestone should prioritize feature delivery over broad compliance/security evidence.

### Pending Todos

- Complete Phase 96 moderation contract and data model readiness docs.
- Implement backend moderation case creation/list/detail/action APIs in Phase 97.
- Implement student/teacher report actions and admin moderation queue/detail UI in Phase 98.
- Run a lightweight functional release gate and update the `stoa_docs` gap audit in Phase 99.

### Blockers/Concerns

- Existing DynamoDB single-table access patterns should be reused unless Phase 96 proves a missing list/filter access pattern.
- Moderation MVP should store enough context for admin triage without turning into a compliance/legal workflow.
- Production verification should avoid customer-content mutation unless a named safe fixture is selected.
- Phase 2 items such as Stripe/TWINT payments, broad multi-subject rollout, student memory, AI teacher tools, WebSocket notifications, and multilingual/mobile polish remain future scope.

## Operator Next Steps

- Execute Phase 96 and proceed to backend moderation APIs.
