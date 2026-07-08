# Roadmap: v6.1 First Cohort Product Remediation Sprint

**Status:** Complete
**Created:** 2026-07-07
**Prior milestone:** v6.0 Real Evidence Capture And Pilot Start Execution

## Goal

Operate the first approved cohort or, if v6.0 remains held, execute the highest-priority blocker fixes required to start that cohort. v6.1 is a product remediation sprint driven by real account/payment/usage/login/notification/support/learning evidence.

## Function Purpose

- Turn v6.0 evidence into shipped fixes instead of more planning.
- Make the first cohort usable enough for parents, students, teachers, and support to complete real learning workflows.
- Keep scope narrow and measurable: fix the highest-impact gaps that block pilot continuation.

## Implementation Strategy

- If v6.0 starts the cohort, run daily review and fix observed failures.
- If v6.0 holds, execute the blocker package until the gate can be rerun.
- Prioritize activation, paid access, usage recording, login/email verification, notification/support visibility, mobile access, and first learning action.
- Add focused regression tests and support-visible release evidence for each fix.

## Phases

- [x] **Phase 377: Cohort Day-One Operations Or Blocker Fix Kickoff** - Start cohort operations or convert v6.0 hold blockers into an execution board. Completed 2026-07-08.
- [x] **Phase 378: Account Login Verification And Role Fixes** - Fix login, email verification, login-code policy, account recovery, role visibility, and admin support gaps. Completed 2026-07-08.
- [x] **Phase 379: Entitlement Usage Notification Support Fixes** - Fix paid access, usage ledger, quota display, notification delivery, support handoff, and teacher dispatch issues. Completed 2026-07-08.
- [x] **Phase 380: First Learning Action And Mobile Friction Fixes** - Fix onboarding, assignment, curriculum, AI/help, mobile/install, and parent/student learning path friction. Completed 2026-07-08.
- [x] **Phase 381: v6.1 Remediation Release Gate** - Decide continue pilot, hold, roll back, or run another blocker sprint. Completed 2026-07-08.

## Phase Details

### Phase 377: Cohort Day-One Operations Or Blocker Fix Kickoff

**Goal**: Convert the v6.0 start decision into either day-one cohort operations or a concrete blocker fix board.
**Depends on**: v6.0 real evidence decision gate.
**Requirements**: V6FIX-01
**Success Criteria**:

1. If v6.0 starts the cohort, day-one activation, support, teacher, notification, usage, entitlement, mobile, and learning signals are reviewed.
2. If v6.0 holds, start-blocking issues are converted into owner/action/fix/test/release rows.
3. Every selected fix has user impact, severity, expected outcome, and verification path.
4. Scope is limited to pilot-critical product behavior.

### Phase 378: Account Login Verification And Role Fixes

**Goal**: Fix or explicitly defer account, login, verification, recovery, session, and role-visibility gaps found by pilot evidence.
**Depends on**: Phase 377.
**Requirements**: V6FIX-02
**Success Criteria**:

1. Login, email verification, resend/confirm, login-code/passwordless policy, account recovery, session expiry, and role visibility are fixed or explicitly deferred.
2. Parent, student, teacher/support, and admin paths have focused tests.
3. Admin/support views explain account state without exposing verification codes or tokens.
4. User copy is clear for blocked, pending, expired, failed, and recovered states.

### Phase 379: Entitlement Usage Notification Support Fixes

**Goal**: Close pilot-critical entitlement, usage, quota, notification, support, and teacher-dispatch gaps.
**Depends on**: Phase 378.
**Requirements**: V6FIX-03
**Success Criteria**:

1. Paid entitlement, checkout/paywall display, subscription state, usage ledger writes, quota reconciliation, and parent/admin explanations are reliable for pilot accounts.
2. Notification delivery and support handoff gaps have fixes, fallbacks, or explicit pilot disablement.
3. Teacher dispatch/SLA visibility is sufficient for pilot support.
4. Evidence links code SHA, request IDs where applicable, and focused test coverage.

### Phase 380: First Learning Action And Mobile Friction Fixes

**Goal**: Make the first useful learning action understandable and reachable across web/mobile access paths.
**Depends on**: Phase 379.
**Requirements**: V6FIX-04
**Success Criteria**:

1. Onboarding, first assignment/practice action, curriculum access, AI/help flow, parent progress view, and mobile install/access friction are fixed or explicitly deferred.
2. Student and parent can understand what to do next without internal operator explanation.
3. Mobile-specific states are tested where local tooling allows.
4. Learning path fixes do not broaden AI autonomy or curriculum-edit permissions.

### Phase 381: v6.1 Remediation Release Gate

**Goal**: Decide whether the first cohort can continue, must hold, must roll back, or needs another blocker sprint.
**Depends on**: Phase 380.
**Requirements**: VERIFY-75
**Success Criteria**:

1. Decision is continue pilot, hold, roll back, or run another blocker sprint.
2. Release evidence includes focused tests, operator notes, user/support copy, and remaining blockers.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. v6.2 is allowed only if account, entitlement, usage, and support risks are controlled enough for paid conversion work.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6FIX-01 | Phase 377 | Complete |
| V6FIX-02 | Phase 378 | Complete |
| V6FIX-03 | Phase 379 | Complete |
| V6FIX-04 | Phase 380 | Complete |
| VERIFY-75 | Phase 381 | Complete |
