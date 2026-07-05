# Roadmap: v5.18 Warehouse BI Observability And Product Analytics Activation

**Status:** Completed
**Created:** 2026-07-05
**Prior milestone:** v5.17 External Provider Activation Smoke And Release Operations

## Goal

Activate operational analytics after product semantics and provider readiness are explicit: aggregate warehouse exports, support-safe operator dashboards, APM/alert routing, and analytics runbooks that separate product regressions from external-provider blockers.

## Why This Follows v5.17

v5.15 stabilized usage/quota semantics, v5.16 proved local product readiness, and v5.17 made provider activation states explicit. v5.18 can now build analytics without mixing real product failures, read-only/local-only readiness, safe-fixture outcomes, and externally blocked provider states.

## Product Purpose

- Operators can see usage, billing readiness, curriculum, teacher help, notification, support, and release-smoke health trends.
- Support and product teams can diagnose issues without raw learning content, provider payloads, private report artifacts, or secrets.
- Release operations produce repeatable metrics and alerts instead of one-off manual evidence.

## Implementation Strategy

- Start with a reality audit to avoid inventing analytics that current code cannot populate.
- Prefer aggregate backend APIs and export contracts before any live third-party BI integration.
- Keep provider-state taxonomy aligned with v5.17 external activation smoke.
- Treat APM/alerts as low-cardinality operational signals, not raw logs.
- Close with honest local/read-only/blocked evidence if live warehouse or alerting credentials are unavailable.

## Phases

- [x] **Phase 262: Analytics Reality Audit And Taxonomy Contract** - Map existing analytics/readiness surfaces, privacy boundaries, provider-state dimensions, and missing evidence before implementation. (completed 2026-07-05)
- [x] **Phase 263: Warehouse Export Job Activation And Schema Evidence** - Implement or enable repeatable aggregate export/readiness outputs with idempotency, bounded scope, backfill/retry semantics, and privacy validation. (completed 2026-07-05)
- [x] **Phase 264: Operator Analytics Dashboard APIs** - Add support-safe aggregate dashboard APIs for usage, billing/provider readiness, curriculum, teacher help, notifications, support, and release-smoke outcomes. (completed 2026-07-05)
- [x] **Phase 265: APM Alert Routing And Observability Runbooks** - Add low-cardinality alert/status contracts and operator runbooks that distinguish product regressions from provider blockers. (completed 2026-07-05)
- [x] **Phase 266: v5.18 BI Observability Release Gate** - Close with focused checks, activation evidence, blocked-prerequisite table, runbooks, and next milestone decision. (completed 2026-07-05)

## Phase Details

### Phase 262: Analytics Reality Audit And Taxonomy Contract

**Goal**: Define exact analytics scope from current code, current data, and v5.17 provider states.
**Requirements**: BI-01
**Success Criteria**:

1. Usage/quota, billing/provider readiness, curriculum analytics/migration, teacher help, notifications, support handoff, core smoke, and external activation smoke surfaces are mapped to code/docs/tests.
2. Dashboard/export dimensions classify live-ready, read-only, safe-fixture, local-only, blocked, failed, and unknown states.
3. Privacy boundaries and forbidden fields are documented before export/dashboard implementation.
4. Missing evidence is routed to Phases 263-265.

### Phase 263: Warehouse Export Job Activation And Schema Evidence

**Goal**: Make aggregate warehouse exports repeatable, bounded, idempotent, and support-safe.
**Requirements**: BI-02
**Success Criteria**:

1. Export/readiness outputs include product surface, period, aggregate counts, status/blocker dimensions, generated timestamp, and privacy metadata.
2. Export generation is idempotent and bounded for local/admin execution.
3. Backfill, retry, partial failure, and stale-data behavior is documented and test-covered.
4. Privacy checks prove raw student content, provider payloads, tokens, secrets, and private S3 keys are excluded.

### Phase 264: Operator Analytics Dashboard APIs

**Goal**: Give operators support-safe analytics views across product and provider readiness surfaces.
**Requirements**: BI-03
**Success Criteria**:

1. Admin dashboard APIs summarize usage/quota, billing/provider readiness, curriculum/editor/migration, teacher-help/support load, notifications, support-provider lifecycle, and release-smoke outcomes.
2. Responses include blocker categories, support actions, stale/partial flags, and provider-state dimensions.
3. Empty, blocked, and unavailable data states are explicit.
4. Tests prove dashboard responses stay aggregate and support-safe.

### Phase 265: APM Alert Routing And Observability Runbooks

**Goal**: Make product regressions and external-provider blockers alertable without leaking private data.
**Requirements**: BI-04
**Success Criteria**:

1. Core flows expose low-cardinality status/error dimensions suitable for APM/alert routing.
2. Alert summaries classify product regression, provider blocker, read-only/local-only state, stale data, and privacy violation separately.
3. Alert payloads avoid high-cardinality private identifiers and raw content.
4. Operator runbooks define severity, ownership, escalation, suppression, retry/backfill, and known blocked states.

### Phase 266: v5.18 BI Observability Release Gate

**Goal**: Close v5.18 with honest analytics activation evidence.
**Requirements**: VERIFY-52
**Success Criteria**:

1. Focused backend checks pass for export/dashboard/alert contracts touched by v5.18.
2. BI activation evidence records live-ready, read-only, local-only, blocked, and failed limitations honestly.
3. Rollback/disable/backfill controls are documented for export, dashboard, and alert surfaces.
4. Docs, roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.

## Future Milestone Directions

- **v5.19 Native Mobile Push And Offline Client Implementation**: implement native/mobile client and push/offline behavior after observability contracts are available.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 262 Analytics Reality Audit And Taxonomy Contract | v5.18 | 1/1 | Complete | 2026-07-05 |
| 263 Warehouse Export Job Activation And Schema Evidence | v5.18 | 1/1 | Complete | 2026-07-05 |
| 264 Operator Analytics Dashboard APIs | v5.18 | 1/1 | Complete | 2026-07-05 |
| 265 APM Alert Routing And Observability Runbooks | v5.18 | 1/1 | Complete | 2026-07-05 |
| 266 v5.18 BI Observability Release Gate | v5.18 | 1/1 | Complete | 2026-07-05 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BI-01 | Phase 262 | Complete |
| BI-02 | Phase 263 | Complete |
| BI-03 | Phase 264 | Complete |
| BI-04 | Phase 265 | Complete |
| VERIFY-52 | Phase 266 | Complete |
