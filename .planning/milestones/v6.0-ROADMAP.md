# Roadmap: v6.0 Real Evidence Capture And Pilot Start Execution

**Status:** Complete
**Created:** 2026-07-07
**Prior milestone:** v5.35-v5.39 Local Contract Completion

## Goal

Start v6 by moving STOA from locally complete launch/pilot contracts into real evidence execution. v6.0 must collect current approved provider, account, support, mobile, restore, monitoring, and cohort evidence, then run the pilot start gate and either start the first cohort or produce a concrete blocker burn-down package.

## Why v6 Starts Now

v5.30-v5.39 exhausted the useful contract-planning loop. The repository now has local gates for pilot start, live operations, revenue conversion, learning quality, and platform scale, but those gates still default to hold/remediation without current real evidence.

Starting v6 is appropriate because the next valuable work is not another v5 contract. It is a new execution track:

- gather real approved evidence,
- run the gates against that evidence,
- fix product gaps discovered by real users,
- convert payment/usage/account/notification/support details into customer-ready behavior,
- scale learning quality and operations only after the pilot proves them.

## Function Purpose

- Convert v5 contract outputs into an executable real-pilot evidence packet.
- Verify the exact user-visible flows that prior testing flagged as incomplete: paid access, usage recording, login/email verification, notification delivery, support/admin visibility, and mobile access.
- Start the first narrow cohort only if `real_pilot_start_decision_gate` returns `start_limited_pilot`.
- If the gate stays held, produce an owner/action burn-down list that can be executed immediately.

## Implementation Strategy

- Treat v5.35-v5.39 contracts as gate surfaces, not proof of launch.
- Use real existing admin/parent/student/teacher accounts or approved secret-backed credential paths.
- Prefer read-only or scoped pilot-safe checks before any production mutation.
- Record only redacted metadata: timestamps, owners, request IDs, build IDs, account aliases, blocker states, and rollback controls.
- Keep public launch, paid marketing, uncontrolled provider writes, and broad expansion out of scope.

## Phases

- [x] **Phase 372: Real Evidence Inventory And Access Readiness** - Reconcile current production/admin/provider/mobile/support access, approvals, and evidence sources needed for v6 execution. Completed 2026-07-08.
- [x] **Phase 373: Account Payment Usage Verification Smoke** - Verify login, email/login-code behavior, entitlement activation, checkout/paywall state, usage ledger, quota display, and admin support visibility with approved accounts. Completed 2026-07-08.
- [x] **Phase 374: Notification Support Mobile And Provider Evidence** - Verify notification delivery state, support handoff, mobile/TestFlight or install path, provider readiness, and disablement fallbacks. Completed 2026-07-08.
- [x] **Phase 375: Pilot Cohort Launch Packet And Dry Run** - Assemble the first cohort packet, communications, support staffing, dashboards, rollback, pause criteria, and dry-run evidence. Completed 2026-07-08.
- [x] **Phase 376: v6.0 Pilot Start Or Blocker Decision Gate** - Run the real pilot start decision and either start the cohort or publish the blocker execution package. Completed 2026-07-08.

## Phase Details

### Phase 372: Real Evidence Inventory And Access Readiness

**Goal**: Reconcile current production, admin, provider, mobile, monitoring, deployment, support, and cohort evidence sources before any pilot execution.
**Depends on**: v5.35-v5.39 local contract completion.
**Requirements**: V6EVID-01
**Success Criteria**:

1. Current admin, parent, student, teacher/support, provider, mobile, monitoring, and deployment access paths are listed with owner and approval state.
2. Required evidence sources are classified as available, missing, disabled for pilot, blocked, or not required.
3. Production checks use real existing sessions/accounts or an approved secret-backed credential path.
4. Evidence excludes secrets, raw provider payloads, raw student content, private object keys, presigned URLs, auth tokens, and verification codes.

### Phase 373: Account Payment Usage Verification Smoke

**Goal**: Verify the highest-risk account, payment, entitlement, usage, quota, and verification flows with approved accounts or explicit blocked states.
**Depends on**: Phase 372.
**Requirements**: V6EVID-02
**Success Criteria**:

1. Login, email verification, login-code/passwordless behavior, account recovery edge states, and role visibility are checked with approved accounts.
2. Paid access, checkout/paywall state, entitlement activation, subscription state, usage ledger writes, quota display, and admin support explanations are checked.
3. Request IDs, account aliases, timestamps, and blocker states are recorded.
4. Any production mutation is explicitly approved, scoped, reversible, and tied to a pilot-safe account.

### Phase 374: Notification Support Mobile And Provider Evidence

**Goal**: Verify or explicitly disable notification, support, mobile, provider, BI/APM, and AI/provider dependencies needed for a narrow pilot.
**Depends on**: Phase 373.
**Requirements**: V6EVID-03
**Success Criteria**:

1. Email, push, and realtime notification delivery state is verified or explicitly disabled for pilot scope with support copy.
2. Support CRM/handoff, support queue, teacher dispatch/SLA visibility, and escalation paths are checked.
3. Mobile/TestFlight/install path and version/build evidence are captured or marked blocked.
4. Payment, notification, support, BI/APM, AI/provider, and mobile blockers have owner, fallback, rollback, and next action.

### Phase 375: Pilot Cohort Launch Packet And Dry Run

**Goal**: Assemble the first cohort operating packet and dry-run the pilot path before any real cohort is enabled.
**Depends on**: Phase 374.
**Requirements**: V6EVID-04
**Success Criteria**:

1. Cohort size, account aliases, communication plan, consent state, support staffing, teacher owner, launch room, dashboards, and rollback authority are documented.
2. Dry run covers login, onboarding, entitlement, usage, first learning action, notification/support touchpoints, mobile path, and admin visibility.
3. Launch packet includes pause criteria, rollback criteria, support macros, known disabled features, and day-one operating plan.
4. Any unresolved gap is marked accepted, disabled for pilot, or start-blocking.

### Phase 376: v6.0 Pilot Start Or Blocker Decision Gate

**Goal**: Run the current real pilot start gate and produce either a narrow cohort start package or an executable blocker package.
**Depends on**: Phase 375.
**Requirements**: VERIFY-74
**Success Criteria**:

1. `production_pilot_service.real_pilot_start_decision_gate` or the current equivalent is run against current evidence.
2. Decision is `start_limited_pilot`, `hold`, or `harden_further`.
3. If started, v6.1 receives cohort scope, dashboards, owners, support coverage, rollback controls, and daily review cadence.
4. If held, v6.1 is not allowed to operate real users and the blocker package becomes the next execution target.

## Future Milestone Directions

- **v6.1 First Cohort Product Remediation Sprint**: operate the cohort and fix user-visible gaps quickly.
- **v6.2 Paid Conversion Usage And Account Reliability Completion**: harden billing, entitlement, usage, verification, lifecycle, and support flows for real parents.
- **v6.3 Learning Outcome And AI Curriculum Quality Sprint**: improve learning quality, curriculum coverage, AI teacher tools, summaries, exercises, and recommendations from real evidence.
- **v6.4 Operations Scale Release And Observability Hardening**: prepare larger cohorts through release discipline, dashboards, support/teacher/admin workflow scale, and reliability.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6EVID-01 | Phase 372 | Complete |
| V6EVID-02 | Phase 373 | Complete |
| V6EVID-03 | Phase 374 | Complete |
| V6EVID-04 | Phase 375 | Complete |
| VERIFY-74 | Phase 376 | Complete |
