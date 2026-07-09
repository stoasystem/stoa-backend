# Roadmap: v6.9 Public Launch Decision And Market Readiness

**Status:** Completed
**Created:** 2026-07-09
**Prior milestone:** v6.8 Learning Outcome And Curriculum Quality Expansion

## Goal

Make an honest market-readiness decision after real pilot, revenue, retention, learning, and operations evidence. v6.9 should decide controlled expansion, public launch preparation, hold, rollback, or another targeted remediation cycle.

## Function Purpose

- Prevent public launch or paid marketing from being approved by optimism.
- Consolidate evidence from cohort operations, revenue, retention, learning quality, support, mobile, provider health, observability, release discipline, and operations.
- Produce a launch/hold decision with owner signoff, rollout scope, support capacity, rollback controls, and user-facing limitations.

## Implementation Strategy

- Treat public launch as an evidence-based decision, not a milestone default.
- Require final owner approval, provider readiness, support staffing, revenue reconciliation, learning quality, mobile readiness, and incident readiness.
- Keep rollout staged and reversible.
- Close with launch prep, controlled expansion, hold, rollback, or v7 recommendation.

## Phases

- [x] **Phase 417: Market Readiness Evidence Consolidation** - Consolidate pilot, revenue, retention, learning, support, mobile, provider, incident, observability, and release evidence.
- [x] **Phase 418: Launch Scope Pricing Support And Risk Review** - Review rollout scope, pricing, package, lifecycle, support staffing, disabled features, and known limitations.
- [x] **Phase 419: App Store Web Production And Provider Readiness Review** - Review frontend/web, mobile/app-store, backend, provider, monitoring, rollback, and incident readiness.
- [x] **Phase 420: Public Launch Or Controlled Expansion Plan** - Prepare staged rollout, communications, growth limits, support plan, dashboards, freeze, rollback, and owner approvals.
- [x] **Phase 421: v6.9 Market Readiness Decision Gate** - Decide launch prep, controlled expansion, hold, rollback, or next version focus.

## Phase Details

### Phase 417: Market Readiness Evidence Consolidation

**Goal**: Consolidate pilot, revenue, retention, learning, support, mobile, provider, incident, observability, and release evidence.
**Depends on**: v6.8 learning expansion decision gate.
**Requirements**: V6MARKET-01
**Success Criteria**:

1. Evidence covers cohort operations, activation, account reliability, revenue, retention, learning quality, support, teacher operations, mobile, provider health, incidents, observability, and release discipline.
2. Evidence distinguishes real users from test, fixture, dry-run, and internal traffic.
3. Risks have owner, severity, user impact, mitigation, rollback, and decision status.
4. Evidence is support-safe and excludes secrets, raw prompts, raw student content, private object keys, and raw provider payloads.

### Phase 418: Launch Scope Pricing Support And Risk Review

**Goal**: Review rollout scope, pricing, package, lifecycle, support staffing, disabled features, and known limitations.
**Depends on**: Phase 417.
**Requirements**: V6MARKET-02
**Success Criteria**:

1. Rollout scope, audience, pricing/package, lifecycle messaging, support staffing, teacher capacity, disabled features, and known limitations are reviewed.
2. Parent/student/teacher/admin copy is ready for included and disabled features.
3. Support macros and incident communications cover billing, login, learning, mobile, AI/provider, and notification issues.
4. Paid marketing remains separate from launch prep unless explicitly approved.

### Phase 419: App Store Web Production And Provider Readiness Review

**Goal**: Review frontend/web, mobile/app-store, backend, provider, monitoring, rollback, and incident readiness.
**Depends on**: Phase 418.
**Requirements**: V6MARKET-03
**Success Criteria**:

1. Backend, frontend/web, mobile/app-store, provider, monitoring, alerting, rollback, migration, and incident readiness are reviewed.
2. Release evidence links code SHA, deploy/build IDs, request IDs where applicable, timestamp, and owner.
3. Provider failures have disablement and fallback controls.
4. App/mobile constraints are explicit if mobile readiness is partial.

### Phase 420: Public Launch Or Controlled Expansion Plan

**Goal**: Prepare staged rollout, communications, growth limits, support plan, dashboards, freeze, rollback, and owner approvals.
**Depends on**: Phase 419.
**Requirements**: V6MARKET-04
**Success Criteria**:

1. Plan states rollout path: public launch prep, controlled expansion, hold, rollback, or remediation.
2. Plan includes cohort/market scope, growth limits, support staffing, dashboards, freeze, rollback, owner approvals, and communications.
3. Known limitations and disabled features are visible to users/support.
4. Public launch does not proceed without final owner approval and healthy evidence.

### Phase 421: v6.9 Market Readiness Decision Gate

**Goal**: Decide launch prep, controlled expansion, hold, rollback, or next version focus.
**Depends on**: Phase 420.
**Requirements**: VERIFY-83
**Success Criteria**:

1. Decision is launch prep, controlled expansion, hold, rollback, or next version focus.
2. Decision uses customer, revenue, learning, support, operations, provider, mobile, and release evidence.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. If v7 is recommended, it is based on remaining real risks, not version-number momentum.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6MARKET-01 | Phase 417 | Completed |
| V6MARKET-02 | Phase 418 | Completed |
| V6MARKET-03 | Phase 419 | Completed |
| V6MARKET-04 | Phase 420 | Completed |
| VERIFY-83 | Phase 421 | Completed |
