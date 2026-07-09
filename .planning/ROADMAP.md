# Roadmap: v6.5 Live Pilot Evidence Execution And Cohort Start

**Status:** Completed
**Created:** 2026-07-09
**Prior milestone:** v6.4 Operations Scale Release And Observability Hardening

## Goal

Execute the first real limited pilot or produce a current blocker package from real production evidence. v6.5 must stop adding local-only gates and instead use approved real accounts, provider evidence, mobile/support evidence, and production read-only smoke results to decide whether the first cohort can start.

## Reality Check

v6.0-v6.4 are locally complete and tested. They provide real-evidence inventory, pilot start, remediation, revenue/account reliability, learning quality, observability, release discipline, and controlled expansion gates.

They still do not prove that real pilot users, provider writes, controlled expansion, paid marketing, or public launch happened. The next useful work is therefore not more contract surface. It is live evidence execution against the existing gates.

## Function Purpose

- Use real existing admin/parent/student/teacher/support accounts or an approved secret-backed credential path.
- Verify production API, account, payment/entitlement, usage, verification, notification, support, mobile, and learning paths with redacted evidence.
- Execute the first cohort start decision from current evidence.
- Keep public launch, paid marketing, broad expansion, and uncontrolled provider writes out of scope.

## Implementation Strategy

- Run production checks read-only by default; use scoped pilot-safe mutations only when explicitly approved.
- Capture redacted request IDs, timestamps, account aliases, build IDs, owner signoffs, blocker states, and rollback controls.
- If a provider or feature is unavailable, mark it disabled for pilot with user copy, support fallback, and owner approval.
- Close with `start_limited_pilot`, `hold`, or `harden_further`.

## Phases

- [x] **Phase 397: Production Evidence Access And Approval Refresh** - Refresh real account/session/provider/mobile/support/deploy access, approvals, and owner signoff.
- [x] **Phase 398: Production Account Payment Usage Smoke** - Verify login, verification, entitlement, checkout/paywall, usage ledger, quota, and admin support state with approved accounts.
- [x] **Phase 399: Production Notification Support Mobile Learning Smoke** - Verify notification/support/mobile/provider/learning paths, or explicitly disable them for pilot with fallback.
- [x] **Phase 400: First Cohort Launch Packet Execution** - Finalize cohort account aliases, communications, support staffing, dashboard, rollback, pause criteria, and dry-run evidence.
- [x] **Phase 401: Live Pilot Start Decision And Handoff** - Run the current gate and hand off either cohort start operations or blocker burn-down.

## Phase Details

### Phase 397: Production Evidence Access And Approval Refresh

**Goal**: Refresh real account/session/provider/mobile/support/deploy access, approvals, and owner signoff.
**Depends on**: v6.4 controlled expansion readiness gate.
**Requirements**: V6LIVE-01
**Success Criteria**:

1. Real admin, parent, student, teacher/support, provider, mobile, monitoring, deploy, and support access paths are refreshed with owner and approval state.
2. Production checks use real existing sessions/accounts or approved secret-backed credentials.
3. Evidence sources are classified as available, missing, disabled for pilot, blocked, or not required.
4. Evidence excludes secrets, auth tokens, verification codes, raw provider payloads, raw student content, private object keys, and presigned URLs.

### Phase 398: Production Account Payment Usage Smoke

**Goal**: Verify login, verification, entitlement, checkout/paywall, usage ledger, quota, and admin support state with approved accounts.
**Depends on**: Phase 397.
**Requirements**: V6LIVE-02
**Success Criteria**:

1. Login, email verification, login-code/passwordless policy, recovery states, role visibility, and admin support visibility are checked.
2. Paid access, checkout/paywall, entitlement activation, subscription state, usage ledger, quota display, and support explanations are checked.
3. Any production mutation is explicitly approved, scoped to pilot-safe accounts, reversible, and recorded.
4. Blockers have owner, severity, user impact, fallback, and next action.

### Phase 399: Production Notification Support Mobile Learning Smoke

**Goal**: Verify notification/support/mobile/provider/learning paths, or explicitly disable them for pilot with fallback.
**Depends on**: Phase 398.
**Requirements**: V6LIVE-03
**Success Criteria**:

1. Notification delivery, support handoff, teacher dispatch/SLA visibility, mobile/TestFlight/install path, AI/provider health, and first learning action are checked.
2. Unavailable features are explicitly disabled for pilot with user copy, support fallback, and owner approval.
3. Evidence includes request/build IDs where applicable and remains support-safe.
4. Smoke results distinguish real production evidence from dry-run or local fixture evidence.

### Phase 400: First Cohort Launch Packet Execution

**Goal**: Finalize cohort account aliases, communications, support staffing, dashboard, rollback, pause criteria, and dry-run evidence.
**Depends on**: Phase 399.
**Requirements**: V6LIVE-04
**Success Criteria**:

1. Cohort account aliases, communication plan, consent state, support staffing, teacher owner, launch room, dashboards, and rollback authority are finalized.
2. Dry run covers login, onboarding, entitlement, usage, first learning action, notification/support touchpoints, mobile path, and admin visibility.
3. Launch packet includes pause criteria, rollback criteria, support macros, known disabled features, and day-one operating plan.
4. Any unresolved gap is accepted, disabled for pilot, or start-blocking.

### Phase 401: Live Pilot Start Decision And Handoff

**Goal**: Run the current gate and hand off either cohort start operations or blocker burn-down.
**Depends on**: Phase 400.
**Requirements**: VERIFY-79
**Success Criteria**:

1. Current pilot start gate is run against the latest real evidence.
2. Decision is `start_limited_pilot`, `hold`, or `harden_further`.
3. If started, v6.6 receives cohort scope, daily operating cadence, owners, dashboards, support coverage, and rollback controls.
4. If held, v6.6 is not allowed to operate real users and the blocker package becomes the next execution target.

## Future Milestone Directions

- **v6.6 First Cohort Live Operations And Fix Sprint**: operate the started cohort and ship real user fixes.
- **v6.7 Revenue Retention And Controlled Growth Execution**: complete paid conversion, lifecycle, retention, and controlled intake from real usage.
- **v6.8 Learning Outcome And Curriculum Quality Expansion**: improve learning quality and curriculum/AI output using real student evidence.
- **v6.9 Public Launch Decision And Market Readiness**: decide controlled expansion, public launch prep, or hold from actual customer and operations evidence.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6LIVE-01 | Phase 397 | Completed |
| V6LIVE-02 | Phase 398 | Completed |
| V6LIVE-03 | Phase 399 | Completed |
| V6LIVE-04 | Phase 400 | Completed |
| VERIFY-79 | Phase 401 | Completed |
