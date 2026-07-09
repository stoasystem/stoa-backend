# Requirements: v6.9 Public Launch Decision And Market Readiness

**Milestone:** v6.9
**Status:** Completed
**Created:** 2026-07-09
**Prior milestone:** v6.8 Learning Outcome And Curriculum Quality Expansion

## Purpose

Make a market-readiness decision from real evidence. v6.9 must decide whether STOA should continue controlled expansion, prepare public launch, hold, roll back, or start a new version focused on remaining risks.

## Requirements

### V6MARKET-01 Market Readiness Evidence Consolidation

Acceptance criteria:

- Evidence covers cohort operations, activation, account reliability, revenue, retention, learning quality, support, teacher operations, mobile, provider health, incidents, observability, and release discipline.
- Evidence distinguishes real users from test, fixture, dry-run, and internal traffic.
- Risks have owner, severity, user impact, mitigation, rollback, and decision status.
- Evidence is support-safe and excludes secrets, raw prompts, raw student content, private object keys, and raw provider payloads.

### V6MARKET-02 Launch Scope Pricing Support And Risk Review

Acceptance criteria:

- Rollout scope, audience, pricing/package, lifecycle messaging, support staffing, teacher capacity, disabled features, and known limitations are reviewed.
- Parent/student/teacher/admin copy is ready for included and disabled features.
- Support macros and incident communications cover billing, login, learning, mobile, AI/provider, and notification issues.
- Paid marketing remains separate from launch prep unless explicitly approved.

### V6MARKET-03 App Store Web Production And Provider Readiness Review

Acceptance criteria:

- Backend, frontend/web, mobile/app-store, provider, monitoring, alerting, rollback, migration, and incident readiness are reviewed.
- Release evidence links code SHA, deploy/build IDs, request IDs where applicable, timestamp, and owner.
- Provider failures have disablement and fallback controls.
- App/mobile constraints are explicit if mobile readiness is partial.

### V6MARKET-04 Public Launch Or Controlled Expansion Plan

Acceptance criteria:

- Plan states rollout path: public launch prep, controlled expansion, hold, rollback, or remediation.
- Plan includes cohort/market scope, growth limits, support staffing, dashboards, freeze, rollback, owner approvals, and communications.
- Known limitations and disabled features are visible to users/support.
- Public launch does not proceed without final owner approval and healthy evidence.

### VERIFY-83 v6.9 Market Readiness Decision Gate

Acceptance criteria:

- Decision is launch prep, controlled expansion, hold, rollback, or next version focus.
- Decision uses customer, revenue, learning, support, operations, provider, mobile, and release evidence.
- Roadmap, requirements, state, milestone snapshots, and project summary are updated.
- If v7 is recommended, it is based on remaining real risks, not version-number momentum.

## Out of Scope

- Public launch without final approval.
- Paid marketing without separate approval and capacity evidence.
- Hiding disabled features or known limitations.
- Unreviewed AI autonomy.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6MARKET-01 | Phase 417 | Completed |
| V6MARKET-02 | Phase 418 | Completed |
| V6MARKET-03 | Phase 419 | Completed |
| V6MARKET-04 | Phase 420 | Completed |
| VERIFY-83 | Phase 421 | Completed |
