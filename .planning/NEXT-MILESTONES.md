# Next Product Milestones

**Updated:** 2026-07-07 after reconciling v5.30-v5.34 live execution contracts with current real-world hold state
**Mode:** feature completion, real pilot execution, revenue conversion, learning quality, and operational scale

## Current Reality

Completed local contract baseline:

- v5.30 added live approval, provider/mobile evidence, restore/tabletop, safe-start, and activation gate contracts.
- v5.31-v5.34 added metadata-only contracts for real pilot operations, live remediation, controlled expansion, public launch, and post-launch operations.
- `PYTHONPATH=src pytest tests/test_production_pilot.py` passed for the contract surfaces.

Important reality check:

- v5.30-v5.34 do not prove real pilot users, provider writes, controlled expansion, paid marketing, or public launch happened.
- The default operational state is still hold unless the live gate returns `start_limited_pilot`.
- The next roadmap must prioritize real blocker burn-down and product completion over more launch abstractions.

## Active: v5.35 Real Pilot Blocker Burn-Down And Launch Execution

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v5.35-ROADMAP.md`
Milestone requirements: `.planning/milestones/v5.35-REQUIREMENTS.md`

Function purpose:

- Clear or explicitly disable the real blockers that keep the pilot gate in `hold`.
- Validate pilot account, support, provider, restore/tabletop, launch-room, monitoring, and rollback readiness.
- Execute the live safe-start gate and start only if the decision is `start_limited_pilot`.

Implementation strategy:

- Use existing v5.30-v5.34 evidence contracts as source of truth.
- Prefer real provider activation where approved; otherwise record explicit pilot disablement with owner, copy, fallback, and support path.
- Keep pilot scope narrow and reversible.

## Planned: v5.36 Live Pilot Operations Feedback And Product Fixes

Roadmap: `.planning/milestones/v5.36-ROADMAP.md`
Requirements: `.planning/milestones/v5.36-REQUIREMENTS.md`

Function purpose:

- Operate the first approved real cohort.
- Turn activation, learning, support, billing, mobile, notification, AI, and teacher evidence into fixes.
- Decide whether to expand, hold, roll back, or continue remediation.

Implementation strategy:

- Start only if v5.35 returns `start_limited_pilot`.
- Run daily review and ship high-impact fixes with focused tests and support-visible release notes.

## Planned: v5.37 Revenue Conversion And Self-Serve Growth Completion

Roadmap: `.planning/milestones/v5.37-ROADMAP.md`
Requirements: `.planning/milestones/v5.37-REQUIREMENTS.md`

Function purpose:

- Finish parent-facing paid conversion, checkout, entitlement activation, quota/usage explanations, billing support, and lifecycle growth loops.
- Make controlled growth possible without billing confusion or support overload.

Implementation strategy:

- Prioritize from real pilot conversion friction and support tickets.
- Reconcile provider state, entitlement state, usage ledger, quota display, invoices/refunds, and admin support views.

## Planned: v5.38 Learning Outcomes Curriculum And AI Quality Scale

Roadmap: `.planning/milestones/v5.38-ROADMAP.md`
Requirements: `.planning/milestones/v5.38-REQUIREMENTS.md`

Function purpose:

- Improve the core learning product: curriculum coverage, exercise quality, adaptive recommendations, AI summaries/exercises, teacher review, and learning outcome reporting.
- Ensure growth is supported by visible learning value, not only operational readiness.

Implementation strategy:

- Use pilot evidence, teacher review, curriculum analytics, and support tickets.
- Keep special authorization for curriculum editing and reviewed/policy-bound AI automation.

## Planned: v5.39 Platform Reliability And Internal Operations Scale

Roadmap: `.planning/milestones/v5.39-ROADMAP.md`
Requirements: `.planning/milestones/v5.39-REQUIREMENTS.md`

Function purpose:

- Harden reliability, observability, data quality, admin operations, teacher/support workflows, incident handling, release discipline, and rollback readiness.
- Prepare the product for larger controlled cohorts without founder-operated manual work.

Implementation strategy:

- Use operational evidence from v5.35-v5.38.
- Prioritize real bottlenecks in support/admin/teacher/release workflows.

## Ordering Rationale

1. v5.35 comes first because the product is still held by real activation blockers.
2. v5.36 follows because real cohort evidence must drive the first product fixes.
3. v5.37 follows because paid conversion and growth should be built from observed customer friction.
4. v5.38 follows because learning quality is the core product value that must scale.
5. v5.39 follows because larger cohorts require repeatable internal operations, reliability, observability, and release discipline.
