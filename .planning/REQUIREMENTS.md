# Requirements: v6.6 First Cohort Live Operations And Fix Sprint

**Milestone:** v6.6
**Status:** Completed
**Created:** 2026-07-09
**Prior milestone:** v6.5 Live Pilot Evidence Execution And Cohort Start

## Purpose

Operate the first real cohort or burn down the v6.5 blockers that prevent it. v6.6 must produce shipped fixes and live operating evidence.

## Requirements

### V6COHORT-01 Cohort Day-One Operations Or Blocker Sprint Start

Acceptance criteria:

- If v6.5 started the cohort, day-one operations cover activation, support, teacher, billing, notification, mobile, usage, and learning signals.
- If v6.5 held, blocker rows include owner, severity, fix path, test path, release path, and target outcome.
- Daily review cadence, pause criteria, rollback authority, and support coverage are active.
- Evidence distinguishes real cohort usage from test, dry-run, and fixture traffic.

### V6COHORT-02 Activation Account Verification And Entitlement Fixes

Acceptance criteria:

- Login, verification, recovery, role visibility, entitlement activation, subscription state, usage writes, quota display, and admin support explanations are fixed or explicitly deferred.
- Parent/student/admin support paths are covered by focused tests.
- User copy is clear for pending, failed, expired, blocked, disabled, and recovered states.
- Revenue-impacting fixes are auditable and reversible.

### V6COHORT-03 Support Teacher Notification Mobile Fixes

Acceptance criteria:

- Support handoff, support queue, teacher dispatch/SLA, escalation, notification delivery, mobile access/install, and incident handling gaps are fixed or explicitly disabled for pilot.
- Operators can see owner, status, next action, and escalation path.
- Notification/mobile/support fallback copy is ready where needed.
- Fix evidence includes request/build IDs where applicable.

### V6COHORT-04 First Learning Action And Parent Clarity Fixes

Acceptance criteria:

- Onboarding, first practice/assignment, curriculum access, AI/help flow, recommendations, and parent progress reporting are usable for the cohort.
- Parent/student flows explain what to do next without operator intervention.
- Learning fixes preserve curriculum authorization and reviewed/policy-bound AI boundaries.
- Known learning gaps are ranked for v6.8.

### VERIFY-80 v6.6 Live Cohort Outcome Gate

Acceptance criteria:

- Decision is continue pilot, hold, rollback, or proceed to revenue/retention execution.
- Decision uses activation, support, teacher, billing, usage, mobile, notification, learning, parent clarity, and incident evidence.
- Roadmap, requirements, state, milestone snapshots, and project summary are updated.
- v6.7 receives only the cohort and revenue risks that remain after v6.6 fixes.

## Out of Scope

- Public launch.
- Paid marketing.
- Cohort expansion without gate approval.
- Broad new product areas unrelated to cohort evidence.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6COHORT-01 | Phase 402 | Completed |
| V6COHORT-02 | Phase 403 | Completed |
| V6COHORT-03 | Phase 404 | Completed |
| V6COHORT-04 | Phase 405 | Completed |
| VERIFY-80 | Phase 406 | Completed |
