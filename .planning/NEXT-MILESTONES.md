# Next Product Milestones

**Updated:** 2026-07-09 after v6.9 local market-readiness decision completion
**Mode:** final approval, controlled expansion, public launch preparation, launch/hold decision, and post-launch scale governance

## Current Reality

Completed local contract baseline:

- v6.0-v6.9 added local contracts and gates for evidence capture, cohort start, cohort operations, revenue retention, learning quality, operations scale, and market-readiness decisions.
- `PYTHONPATH=src pytest tests/test_production_pilot.py` passed with 73 tests and focused Ruff passed in the v6.9 audit.
- v6.9 closed as a market-readiness decision contract only.

Important reality check:

- v6.9 does not approve public launch, paid marketing, uncontrolled provider writes, or broad expansion by itself.
- Public launch prep is possible only with clear evidence, final owner approval, and healthy live evidence.
- Paid marketing remains separately gated.

## Active: v7.0 Final Live Approval And Controlled Expansion Start

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v7.0-ROADMAP.md`
Milestone requirements: `.planning/milestones/v7.0-REQUIREMENTS.md`

Function purpose:

- Convert v6.9 launch/expansion decision inputs into final real approval.
- Start a larger controlled cohort only if current evidence is healthy.
- Keep broad public launch and paid marketing blocked unless later milestones explicitly approve them.

Implementation strategy:

- Refresh final owner approval, support capacity, provider/mobile state, revenue reconciliation, learning quality, and incident readiness.
- Run production checks read-only by default and use only approved, scoped, reversible expansion actions.
- Close with controlled expansion start, hold, rollback, or remediation.

## Planned: v7.1 Controlled Expansion Operations And Remediation

Roadmap: `.planning/milestones/v7.1-ROADMAP.md`
Requirements: `.planning/milestones/v7.1-REQUIREMENTS.md`

Function purpose:

- Operate the approved controlled expansion cohort.
- Fix real bottlenecks across account, billing, usage, support, teacher operations, mobile, AI/provider, curriculum, notifications, and reliability.

Implementation strategy:

- Run daily controlled-expansion review.
- Rank issues by severity, frequency, support load, revenue impact, learning impact, and rollout risk.
- Close with public-launch-prep, continue expansion, hold, rollback, or remediation.

## Planned: v7.2 Public Launch Preparation And Acquisition Readiness

Roadmap: `.planning/milestones/v7.2-ROADMAP.md`
Requirements: `.planning/milestones/v7.2-REQUIREMENTS.md`

Function purpose:

- Prepare public launch only if controlled expansion evidence is healthy.
- Finalize launch scope, pricing/package, web/mobile/app-store readiness, support staffing, lifecycle messaging, acquisition limits, waitlist/referral intake, provider readiness, and owner approvals.

Implementation strategy:

- Use v7.1 evidence as the launch-readiness input.
- Keep paid marketing separately gated.
- Close with launch-ready, controlled-expansion-only, hold, rollback, or remediation.

## Planned: v7.3 Public Launch Execution Or Hold Decision

Roadmap: `.planning/milestones/v7.3-ROADMAP.md`
Requirements: `.planning/milestones/v7.3-REQUIREMENTS.md`

Function purpose:

- Execute staged public launch only if final approval and healthy evidence exist.
- Otherwise continue controlled expansion, hold, rollback, or remediate.

Implementation strategy:

- Reconfirm final owner approval, support capacity, provider readiness, mobile/app-store readiness, revenue reconciliation, learning quality, and rollback authority.
- Use staged rollout, freeze controls, live monitoring, and daily launch-room review.

## Planned: v7.4 Post-Launch Scale Customer Success And Growth Governance

Roadmap: `.planning/milestones/v7.4-ROADMAP.md`
Requirements: `.planning/milestones/v7.4-REQUIREMENTS.md`

Function purpose:

- Operate the post-launch or post-expansion system at scale.
- Govern customer success, support operations, revenue reconciliation, learning quality, growth, mobile/provider reliability, incidents, and roadmap feedback.

Implementation strategy:

- Use v7.3 outcome as the operating mode: launched, controlled expansion, hold, rollback, or remediation.
- Keep paid marketing spend gated by support/revenue/learning capacity.
- Close with scale, hold, rollback, remediation, or v8 recommendation.

## Ordering Rationale

1. v7.0 comes first because v6.9 is a decision contract, not final approval.
2. v7.1 follows because controlled expansion must produce operational evidence before public launch prep.
3. v7.2 follows because public launch preparation should depend on controlled expansion health.
4. v7.3 follows because launch execution must be a go/no-go decision with final evidence.
5. v7.4 follows because launch or expansion needs post-launch governance, customer success, and scale controls.
