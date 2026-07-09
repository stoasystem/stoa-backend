# Next Product Milestones

**Updated:** 2026-07-09 after v6.4 local operations scale completion
**Mode:** live evidence execution, first cohort operations, revenue retention, learning quality, and market readiness

## Current Reality

Completed local contract baseline:

- v6.0-v6.4 added local real-evidence, first-cohort remediation, revenue/account reliability, learning quality, operations risk, workflow scale, observability, release discipline, and controlled expansion gates.
- `PYTHONPATH=src pytest tests/test_production_pilot.py` passed with 48 tests and focused Ruff passed in the v6.4 audit.
- v6.4 closed as local-contract readiness only.

Important reality check:

- v5.30-v6.4 do not prove real pilot users, provider writes, controlled expansion, paid marketing, or public launch happened.
- Current gates still default to hold or remediation without current approved real evidence.
- The next five milestones must execute real evidence and customer/product loops, not add more local-only gates.

## Active: v6.5 Live Pilot Evidence Execution And Cohort Start

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v6.5-ROADMAP.md`
Milestone requirements: `.planning/milestones/v6.5-REQUIREMENTS.md`

Function purpose:

- Use approved real accounts/sessions or approved secret-backed credentials.
- Verify production account, payment, entitlement, usage, verification, notification, support, mobile, provider, and learning paths.
- Start the first cohort only if current evidence supports `start_limited_pilot`; otherwise publish a blocker package.

Implementation strategy:

- Production checks are read-only by default.
- Scoped pilot-safe mutations require explicit approval and rollback.
- Record redacted request IDs, timestamps, account aliases, build IDs, owner signoffs, blocker states, and rollback controls.

## Planned: v6.6 First Cohort Live Operations And Fix Sprint

Roadmap: `.planning/milestones/v6.6-ROADMAP.md`
Requirements: `.planning/milestones/v6.6-REQUIREMENTS.md`

Function purpose:

- Operate the started cohort or execute v6.5 blocker fixes.
- Ship real user fixes across activation, account, entitlement, usage, support, notification, mobile, teacher help, and first learning action.

Implementation strategy:

- Run daily pilot review if cohort starts.
- Use the blocker package as the sprint backlog if v6.5 holds.
- Rank fixes by severity, frequency, learning impact, support load, and revenue impact.

## Planned: v6.7 Revenue Retention And Controlled Growth Execution

Roadmap: `.planning/milestones/v6.7-ROADMAP.md`
Requirements: `.planning/milestones/v6.7-REQUIREMENTS.md`

Function purpose:

- Prove paid conversion, entitlement, usage/quota, lifecycle, retention, support capacity, referral/waitlist intake, and revenue reconciliation under real conditions.
- Decide controlled growth, hold, rollback, or revenue remediation.

Implementation strategy:

- Use v6.5-v6.6 cohort evidence and support tickets.
- Reconcile provider, entitlement, usage, quota, invoice/refund, lifecycle, and support states.
- Keep growth intake gated by capacity and support readiness.

## Planned: v6.8 Learning Outcome And Curriculum Quality Expansion

Roadmap: `.planning/milestones/v6.8-ROADMAP.md`
Requirements: `.planning/milestones/v6.8-REQUIREMENTS.md`

Function purpose:

- Improve student progress, weak-topic remediation, curriculum, exercises, AI teacher output, adaptive recommendations, and parent progress clarity from real evidence.
- Ensure growth depends on visible learning value.

Implementation strategy:

- Rank learning issues by real frequency, severity, student impact, teacher effort, and parent confusion.
- Keep curriculum editing specially authorized and AI automation reviewed or policy-bound.

## Planned: v6.9 Public Launch Decision And Market Readiness

Roadmap: `.planning/milestones/v6.9-ROADMAP.md`
Requirements: `.planning/milestones/v6.9-REQUIREMENTS.md`

Function purpose:

- Consolidate pilot, revenue, retention, learning, support, mobile, provider, observability, incident, and release evidence.
- Decide public launch prep, controlled expansion, hold, rollback, or next version focus.

Implementation strategy:

- Treat public launch as an evidence-based decision, not a milestone default.
- Require owner approval, provider readiness, support staffing, revenue reconciliation, learning quality, mobile readiness, and incident readiness.

## Ordering Rationale

1. v6.5 comes first because current approved real evidence is still missing from the local contract chain.
2. v6.6 follows because the first cohort or blocker package must drive shipped fixes.
3. v6.7 follows because growth requires reliable paid conversion, retention, support, and revenue reconciliation.
4. v6.8 follows because learning quality must prove customer value before market expansion.
5. v6.9 follows because public launch or controlled expansion should be a decision from real evidence, not a version-number default.
