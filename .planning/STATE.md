---
gsd_state_version: 1.0
milestone: v3.4
milestone_name: Learning Expansion Foundation
status: planning
last_updated: "2026-06-08T15:34:28+02:00"
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
**Current focus:** v3.4 learning expansion foundation.

## Current Position

Phase: 104 Multi-Subject Taxonomy And Prompt Contract
Plan: 104-01
Status: Planned.
Last activity: 2026-06-08 - reviewed `stoa_docs` after v3.3 and selected learning expansion foundation as the next product-building milestone.

## Accumulated Context

### Decisions

- v3.0 closed account lifecycle, parent binding, OCR correction, daily quota hardening, and v2.9 production verification gaps from `stoa_docs`.
- v3.1 closed teacher rich text/formula replies and response-time SLA tracking.
- v3.2 shipped content moderation report actions, moderation cases, admin queue/detail/actions, deploy evidence, and production-safe smoke.
- v3.3 completed manual subscription operations and deferred actual payment-provider integration.
- v3.4 starts with learning expansion foundation because `stoa_docs` Phase 2 calls for multi-subject support, student memory/personalization, and AI teacher tools; a stable taxonomy/profile foundation should come before broad curriculum or exercise generation.

### Pending Todos

- Complete Phase 104 multi-subject taxonomy and prompt contract docs.
- Implement backend subject/topic support and student profile seeds in Phase 105.
- Implement student/parent learning profile UI in Phase 106.
- Run lightweight functional release gate and update gap tracking in Phase 107.

### Blockers/Concerns

- v3.4 should not claim a full multi-subject curriculum rollout.
- Automatic exercise generation and full long-term student memory remain future scope.
- Existing math flows must remain backward compatible.
- Internal development should focus on functional progress, not broad compliance/security evidence.

## Operator Next Steps

- Execute Phase 104 and proceed to backend learning expansion foundations.
