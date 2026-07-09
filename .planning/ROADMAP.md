# Roadmap: v6.6 First Cohort Live Operations And Fix Sprint

**Status:** Completed
**Created:** 2026-07-09
**Prior milestone:** v6.5 Live Pilot Evidence Execution And Cohort Start

## Goal

Operate the first approved cohort if v6.5 starts it, or execute the v6.5 blocker package until a cohort can start. v6.6 must convert real user evidence into shipped fixes across activation, account state, billing, usage, support, mobile, notification, teacher help, and first learning action.

## Function Purpose

- Make the first real cohort usable enough to continue.
- Fix concrete user-facing failures instead of adding more readiness surfaces.
- Preserve a daily operating cadence with rollback and pause authority.

## Implementation Strategy

- If v6.5 returns `start_limited_pilot`, run daily pilot operations.
- If v6.5 returns `hold`, treat the blocker package as the sprint backlog.
- Rank fixes by severity, frequency, learning impact, support load, and revenue impact.
- Ship focused tests, rollback notes, and support-visible release evidence.

## Phases

- [x] **Phase 402: Cohort Day-One Operations Or Blocker Sprint Start** - Start cohort operations or convert v6.5 blockers into a fix board.
- [x] **Phase 403: Activation Account Verification And Entitlement Fixes** - Fix login, verification, role, entitlement, subscription, usage, quota, and admin support gaps.
- [x] **Phase 404: Support Teacher Notification Mobile Fixes** - Fix support handoff, teacher dispatch/SLA, notification delivery, mobile install/access, and incident escalation gaps.
- [x] **Phase 405: First Learning Action And Parent Clarity Fixes** - Fix onboarding, curriculum/practice access, AI/help flow, recommendations, and parent progress clarity.
- [x] **Phase 406: v6.6 Live Cohort Outcome Gate** - Decide continue pilot, hold, rollback, or proceed to revenue/retention execution.

## Phase Details

### Phase 402: Cohort Day-One Operations Or Blocker Sprint Start

**Goal**: Start cohort operations or convert v6.5 blockers into a fix board.
**Depends on**: v6.5 live pilot start decision.
**Requirements**: V6COHORT-01
**Success Criteria**:

1. If v6.5 started the cohort, day-one operations cover activation, support, teacher, billing, notification, mobile, usage, and learning signals.
2. If v6.5 held, blocker rows include owner, severity, fix path, test path, release path, and target outcome.
3. Daily review cadence, pause criteria, rollback authority, and support coverage are active.
4. Evidence distinguishes real cohort usage from test, dry-run, and fixture traffic.

### Phase 403: Activation Account Verification And Entitlement Fixes

**Goal**: Fix login, verification, role, entitlement, subscription, usage, quota, and admin support gaps.
**Depends on**: Phase 402.
**Requirements**: V6COHORT-02
**Success Criteria**:

1. Login, verification, recovery, role visibility, entitlement activation, subscription state, usage writes, quota display, and admin support explanations are fixed or explicitly deferred.
2. Parent/student/admin support paths are covered by focused tests.
3. User copy is clear for pending, failed, expired, blocked, disabled, and recovered states.
4. Revenue-impacting fixes are auditable and reversible.

### Phase 404: Support Teacher Notification Mobile Fixes

**Goal**: Fix support handoff, teacher dispatch/SLA, notification delivery, mobile install/access, and incident escalation gaps.
**Depends on**: Phase 403.
**Requirements**: V6COHORT-03
**Success Criteria**:

1. Support handoff, support queue, teacher dispatch/SLA, escalation, notification delivery, mobile access/install, and incident handling gaps are fixed or explicitly disabled for pilot.
2. Operators can see owner, status, next action, and escalation path.
3. Notification/mobile/support fallback copy is ready where needed.
4. Fix evidence includes request/build IDs where applicable.

### Phase 405: First Learning Action And Parent Clarity Fixes

**Goal**: Fix onboarding, curriculum/practice access, AI/help flow, recommendations, and parent progress clarity.
**Depends on**: Phase 404.
**Requirements**: V6COHORT-04
**Success Criteria**:

1. Onboarding, first practice/assignment, curriculum access, AI/help flow, recommendations, and parent progress reporting are usable for the cohort.
2. Parent/student flows explain what to do next without operator intervention.
3. Learning fixes preserve curriculum authorization and reviewed/policy-bound AI boundaries.
4. Known learning gaps are ranked for v6.8.

### Phase 406: v6.6 Live Cohort Outcome Gate

**Goal**: Decide continue pilot, hold, rollback, or proceed to revenue/retention execution.
**Depends on**: Phase 405.
**Requirements**: VERIFY-80
**Success Criteria**:

1. Decision is continue pilot, hold, rollback, or proceed to revenue/retention execution.
2. Decision uses activation, support, teacher, billing, usage, mobile, notification, learning, parent clarity, and incident evidence.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. v6.7 receives only the cohort and revenue risks that remain after v6.6 fixes.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6COHORT-01 | Phase 402 | Completed |
| V6COHORT-02 | Phase 403 | Completed |
| V6COHORT-03 | Phase 404 | Completed |
| V6COHORT-04 | Phase 405 | Completed |
| VERIFY-80 | Phase 406 | Completed |
