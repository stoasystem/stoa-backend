# Roadmap: v6.4 Operations Scale Release And Observability Hardening

**Status:** Completed
**Created:** 2026-07-07
**Prior milestone:** v6.3 Learning Outcome And AI Curriculum Quality Sprint

## Goal

Prepare STOA for a larger controlled cohort by hardening observability, support/admin/teacher workflows, release discipline, rollback, migration safety, incident handling, and operational ownership.

## Function Purpose

- Make the system operable by a small team without founder-only manual coordination.
- Catch reliability, billing, notification, support, teacher dispatch, AI/provider, mobile, and release issues before users report them.
- Make expansion decisions based on live operational evidence.

## Implementation Strategy

- Use v6.0-v6.3 evidence as the risk register.
- Prioritize high-frequency operator tasks and high-severity failure modes.
- Tie dashboards and alerts to owners and runbooks.
- Close with larger cohort readiness, hold, rollback, or another hardening cycle.

## Phases

- [x] **Phase 392: Operations Risk And Incident Review** - Review incidents, near misses, manual toil, data drift, provider degradation, and support/teacher bottlenecks.
- [x] **Phase 393: Admin Support Teacher Workflow Scale Fixes** - Improve account operations, billing support, teacher dispatch, support handoff, content operations, and escalation workflows.
- [x] **Phase 394: Observability Alert And Dashboard Hardening** - Tune dashboards and alerts for auth, billing, usage, notification, support, teacher, AI/provider, mobile, curriculum, and revenue.
- [x] **Phase 395: Release Migration Rollback And Smoke Discipline** - Harden release checklist, migrations, rollback, smoke tests, fixture hygiene, deploy evidence, and owner handoff.
- [x] **Phase 396: v6.4 Controlled Expansion Readiness Gate** - Decide larger cohort, hold, rollback, or another operations hardening cycle.

## Phase Details

### Phase 392: Operations Risk And Incident Review

**Goal**: Review incidents, near misses, manual toil, data drift, provider degradation, and support/teacher bottlenecks.
**Depends on**: v6.3 learning quality gate.
**Requirements**: V6OPS-01
**Success Criteria**:

1. Recent incidents, near misses, manual toil, data drift, provider degradation, support bottlenecks, teacher queue issues, and release regressions are reviewed.
2. Each issue has severity, owner, user impact, recurrence risk, detection path, and remediation status.
3. Product, reliability, support, and process gaps are separated.
4. Highest-risk findings are selected for implementation.

### Phase 393: Admin Support Teacher Workflow Scale Fixes

**Goal**: Improve account operations, billing support, teacher dispatch, support handoff, content operations, and escalation workflows.
**Depends on**: Phase 392.
**Requirements**: V6OPS-02
**Success Criteria**:

1. Account operations, billing support, teacher dispatch, support handoff, content operations, curriculum QA, and escalation workflows are improved based on real bottlenecks.
2. Sensitive operations remain admin-only or specially authorized.
3. Operators can see state, owner, next action, and escalation path without private content leakage.
4. Manual work is reduced where it causes delays or errors.

### Phase 394: Observability Alert And Dashboard Hardening

**Goal**: Tune dashboards and alerts for auth, billing, usage, notification, support, teacher, AI/provider, mobile, curriculum, and revenue.
**Depends on**: Phase 393.
**Requirements**: V6OPS-03
**Success Criteria**:

1. Dashboards cover auth, entitlement, usage, billing, notification, support SLA, teacher dispatch, AI/provider health, mobile, curriculum/content, incidents, and revenue.
2. Alerts have owner, threshold, severity, escalation path, false-positive review, and runbook link.
3. Evidence distinguishes test, dry-run, pilot, and real customer traffic.
4. Dashboards and alert evidence exclude secrets, raw prompts, raw student content, private object keys, and raw provider payloads.

### Phase 395: Release Migration Rollback And Smoke Discipline

**Goal**: Harden release checklist, migrations, rollback, smoke tests, fixture hygiene, deploy evidence, and owner handoff.
**Depends on**: Phase 394.
**Requirements**: V6OPS-04
**Success Criteria**:

1. Backend, frontend, mobile, provider, migration, and configuration changes have a current release checklist.
2. High-risk changes have staged rollout, feature flag, rollback, and smoke coverage.
3. Release evidence links code SHA, deploy/build IDs, request IDs where applicable, timestamp, and owner.
4. Rollback and recovery instructions are executable by the assigned operator.

### Phase 396: v6.4 Controlled Expansion Readiness Gate

**Goal**: Decide larger controlled cohort, hold, rollback, or another operations hardening cycle.
**Depends on**: Phase 395.
**Requirements**: VERIFY-78
**Success Criteria**:

1. Decision is larger controlled cohort, hold, rollback, or another hardening cycle.
2. Decision uses incident, support, teacher, billing, data quality, mobile, provider, learning, and release evidence.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. Next version recommendation is based on real bottlenecks and customer outcomes.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6OPS-01 | Phase 392 | Completed |
| V6OPS-02 | Phase 393 | Completed |
| V6OPS-03 | Phase 394 | Completed |
| V6OPS-04 | Phase 395 | Completed |
| VERIFY-78 | Phase 396 | Completed |
