# Next Product Milestones

**Updated:** 2026-07-09 after v7.0-v7.4 local gated rollout contract completion
**Mode:** external rollout execution, live operations, revenue growth, learning scale, and strategic scale decision

## Current Reality

Completed local contract baseline:

- v7.0-v7.4 added local gated contracts for final controlled expansion approval, controlled expansion operations, public launch preparation, public launch execution or hold, and post-launch scale governance.
- `PYTHONPATH=src pytest tests/test_production_pilot.py` passed with 78 tests and focused Ruff passed.
- v7.4 closed as a local gated operations contract.

Important reality check:

- v7.0-v7.4 do not approve real controlled expansion, public launch, paid marketing, broad expansion, uncontrolled provider writes, or external customer rollout by themselves.
- Real rollout actions require explicit owner approval, healthy live evidence, scoped accounts, rollback controls, and support-ready operations.
- v8 must be the hard execution boundary: live evidence and approval in, external rollout action or hold out.

## Active: v8.0 External Rollout Approval And Live Evidence Execution

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v8.0-ROADMAP.md`
Milestone requirements: `.planning/milestones/v8.0-REQUIREMENTS.md`

Function purpose:

- Convert v7 gate outputs into final live rollout approval or a current hold/remediation package.
- Verify production product paths with real or approved secret-backed sessions.
- Make external rollout action scoped, reversible, support-ready, and evidence-backed.

Implementation strategy:

- Use read-only production checks by default.
- Allow only explicitly approved, scoped, reversible rollout actions.
- Close with rollout start, hold, rollback, or remediation.

## Planned: v8.1 Live Rollout Operations And Incident Remediation

Roadmap: `.planning/milestones/v8.1-ROADMAP.md`
Requirements: `.planning/milestones/v8.1-REQUIREMENTS.md`

Function purpose:

- Operate the approved external rollout if v8.0 starts it, or execute the v8.0 blocker package if rollout remains held.
- Convert live customer, support, revenue, learning, mobile, provider, and incident evidence into fixes.

Implementation strategy:

- Run daily rollout operations with product, support, teacher, finance, mobile, provider, and incident owners.
- Ship hotfixes and product fixes with tests, release evidence, support copy, and rollback notes.

## Planned: v8.2 Revenue Growth Acquisition And Paid Marketing Gate

Roadmap: `.planning/milestones/v8.2-ROADMAP.md`
Requirements: `.planning/milestones/v8.2-REQUIREMENTS.md`

Function purpose:

- Evaluate and execute the next growth step only if rollout operations are healthy.
- Keep paid marketing separately gated by capacity, economics, learning quality, and owner approval.

Implementation strategy:

- Reconcile revenue, retention, churn, refunds, failed payments, usage/quota, pricing, lifecycle, and support corrections.
- Gate paid marketing by support capacity, revenue quality, learning quality, incident readiness, and owner approval.

## Planned: v8.3 Learning Outcomes Scale And AI Curriculum Improvement

Roadmap: `.planning/milestones/v8.3-ROADMAP.md`
Requirements: `.planning/milestones/v8.3-REQUIREMENTS.md`

Function purpose:

- Protect and improve learning outcomes as rollout and growth increase.
- Improve curriculum, AI teacher quality, adaptive recommendations, parent progress, teacher workload, and support burden.

Implementation strategy:

- Review learning outcomes across cohorts and acquisition sources.
- Keep curriculum authorization and AI review boundaries intact.

## Planned: v8.4 Strategic Scale Reliability And Next-Version Decision

Roadmap: `.planning/milestones/v8.4-ROADMAP.md`
Requirements: `.planning/milestones/v8.4-REQUIREMENTS.md`

Function purpose:

- Make a strategic scale decision after live rollout, growth, revenue, learning, support, and operations evidence.
- Decide scale growth, hold, rollback, remediation, market expansion, enterprise readiness, or v9 focus.

Implementation strategy:

- Review product, revenue, learning, support, teacher, mobile, provider, incident, reliability, acquisition, and strategic evidence.
- Keep market/language expansion, enterprise sales, paid marketing scale, and AI autonomy separately approved.

## Ordering Rationale

1. v8.0 comes first because v7 is still local gated contracts, not external rollout approval.
2. v8.1 follows because live rollout evidence must drive operational fixes.
3. v8.2 follows because growth and paid marketing require healthy rollout, revenue, support, and learning evidence.
4. v8.3 follows because learning outcomes must hold as growth increases.
5. v8.4 follows because strategic scale decisions should come from live product and business evidence.
