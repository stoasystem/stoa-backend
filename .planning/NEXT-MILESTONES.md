# Next Product Milestones

**Updated:** 2026-07-08 after v6.4 local operations scale completion
**Mode:** real evidence execution, pilot start, product remediation, revenue reliability, learning quality, and operational scale

## Current Reality

Completed local contract baseline:

- v5.30-v5.34 added metadata-only contracts for live pilot approval, real pilot operations, remediation, controlled expansion, public launch, and post-launch operations.
- v5.35-v5.39 added metadata-only contracts for real pilot start, live operations feedback, revenue conversion, learning quality, and platform/internal operations scale.
- v6.0-v6.4 added local real-evidence, first-cohort remediation, revenue/account reliability, learning quality, operations risk, workflow scale, observability, release discipline, and controlled expansion gates.
- `PYTHONPATH=src pytest tests/test_production_pilot.py` and focused Ruff are recorded as passing in the v6.4 evidence.

Important reality check:

- v5.30-v6.4 do not prove real pilot users, provider writes, controlled expansion, paid marketing, or public launch happened.
- Current gates still default to hold or remediation without current approved real evidence.
- v6 is not a public-launch label. It is the real evidence execution track.

## Completed: v6.0 Real Evidence Capture And Pilot Start Execution

Milestone roadmap: `.planning/milestones/v6.0-ROADMAP.md`
Milestone requirements: `.planning/milestones/v6.0-REQUIREMENTS.md`

Function purpose:

- Gather current approved real evidence for admin/parent/student/teacher accounts, providers, mobile, support, monitoring, restore/tabletop, and cohort readiness.
- Verify paid access, usage recording, login/email verification, notification/support visibility, and mobile paths.
- Run the real pilot start gate and either start the first cohort or publish a blocker execution package.

Implementation strategy:

- Treat v5 contracts as gate surfaces, not proof of launch.
- Use real existing sessions/accounts or approved secret-backed credential paths.
- Record redacted metadata only and keep public launch, paid marketing, broad expansion, and uncontrolled provider writes out of scope.

## Completed: v6.1 First Cohort Product Remediation Sprint

Roadmap: `.planning/milestones/v6.1-ROADMAP.md`
Requirements: `.planning/milestones/v6.1-REQUIREMENTS.md`

Function purpose:

- Operate the first approved cohort or execute v6.0 blocker fixes.
- Fix user-visible gaps in account/login, entitlement, usage, notification, support, mobile, and first learning action.

Implementation strategy:

- If v6.0 starts, run daily cohort review.
- If v6.0 holds, execute the blocker package until the gate can be rerun.
- Ship focused fixes with regression tests and support-visible evidence.

## Completed: v6.2 Paid Conversion Usage And Account Reliability Completion

Roadmap: `.planning/milestones/v6.2-ROADMAP.md`
Requirements: `.planning/milestones/v6.2-REQUIREMENTS.md`

Function purpose:

- Complete checkout/paywall, entitlement activation, subscription state, usage ledger, quota reconciliation, verification lifecycle, billing support, and lifecycle messaging.
- Make paid access understandable and reliable for real parents.

Implementation strategy:

- Use v6.0/v6.1 evidence and support tickets.
- Reconcile billing provider state, entitlement state, usage state, quota display, and admin/support state.

## Completed: v6.3 Learning Outcome And AI Curriculum Quality Sprint

Roadmap: `.planning/milestones/v6.3-ROADMAP.md`
Requirements: `.planning/milestones/v6.3-REQUIREMENTS.md`

Function purpose:

- Improve curriculum coverage, exercise quality, adaptive recommendations, AI summaries/exercises, teacher review, parent progress reporting, and first-week learning retention.
- Ensure growth is supported by real learning value.

Implementation strategy:

- Prioritize real weak-topic, support, teacher, and parent feedback.
- Keep curriculum editing restricted to specially authorized operators and AI automation reviewed or policy-bound.

## Completed: v6.4 Operations Scale Release And Observability Hardening

Roadmap: `.planning/milestones/v6.4-ROADMAP.md`
Requirements: `.planning/milestones/v6.4-REQUIREMENTS.md`

Function purpose:

- Harden observability, support/admin/teacher workflows, release discipline, rollback, migration safety, incident handling, and operational ownership.
- Prepare for larger controlled cohorts only after v6.0-v6.3 evidence supports it.

Implementation strategy:

- Use v6.0-v6.3 evidence as the risk register.
- Prioritize high-frequency operator tasks and high-severity failure modes.

## Ordering Rationale

1. v6.0 comes first because v5 contracts need current real evidence before users can be enabled.
2. v6.1 follows because real evidence should drive immediate product fixes.
3. v6.2 follows because paid access, usage, verification, and account reliability are business-critical before growth.
4. v6.3 follows because learning quality is the core customer value.
5. v6.4 follows because larger cohorts need repeatable operations, observability, releases, support, and rollback.
