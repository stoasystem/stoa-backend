# Phase 161 Context: Support Provider Expansion Contract And Adapter Readiness

## Why This Phase Exists

v4.5 connected support-safe evidence packages to a controlled internal queue and made handoff status visible to operators. That left the higher-value `stoa_docs` operations gap: approved third-party support provider adapters, retry workers, two-way ticket synchronization, SLA analytics, and controlled CRM/customer messaging.

v4.8 starts with a contract phase so provider writes, retries, sync, and messaging have a stable implementation boundary before code expands beyond the internal queue.

## Current Foundation

- v2.4 created support-safe handoff packages from recovery, release, fixture, and operator-note evidence.
- v2.5 production-verified support handoff read/write behavior for the internal workflow without external support-system writes.
- v4.5 defined support destination contracts, selected `internal_queue` as the first approved path, added delivery queue/detail visibility, and preserved metadata-only support evidence boundaries.
- `stoa_docs` remaining feature queue now recommends support provider expansion and CRM automation.

## Phase Boundary

This phase is planning/contract work. It should define what Phase 162 through Phase 165 implement and what remains externally blocked. It should not perform real third-party support/CRM writes.

## Key Files To Inspect

- `src/stoa/routers/admin.py`
- `src/stoa/services/support_handoff_service.py`
- `src/stoa/services/support_destination_service.py`
- `src/stoa/services/report_operations_service.py`
- `tests/test_support_handoff.py`
- `tests/test_admin_report_operations.py`
- `.planning/phases/148-support-destination-contract-and-credential-readiness/`
- `.planning/phases/149-support-evidence-export-destination-integration/`
- `.planning/phases/150-operator-queue-and-handoff-status-visibility/`
- `.planning/phases/151-v4-5-support-integration-release-gate/`

## Constraints

- Third-party support or CRM writes require explicit destination approval and configured credentials.
- Support payloads must stay metadata-only and must not include raw report artifacts, raw report JSON/HTML, presigned URLs, auth tokens, or raw private provider payloads.
- Retry and sync behavior must be idempotent and operator-visible.
- Customer messaging must be template-gated and tied to support events rather than broad marketing campaigns.
- Verification should focus on functional behavior and boundaries needed for internal development.
