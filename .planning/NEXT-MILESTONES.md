# Next Product Milestones

**Updated:** 2026-07-07 after reconciling v5.25-v5.29 local contract completion with real-user execution gates
**Mode:** live approval, real pilot execution, live remediation, controlled expansion, and public launch operations

## Current Reality

Completed local contract baseline:

- v5.24 produced conditional limited-pilot readiness.
- v5.25 added safe-start blocker burn-down contracts and defaults to `hold`.
- v5.26-v5.29 added local metadata-only contracts for pilot execution controls, outcome decisions, remediation gates, expansion gates, and public-launch readiness gates.

Important reality check:

- No real pilot users are approved by the local contracts.
- No provider writes, controlled expansion, paid marketing, or public launch are approved.
- Real-user execution remains gated by explicit operational approval and live provider/readiness evidence.
- The default current state is hold until `pilot_safe_start_gate` returns `start_limited_pilot`.

## Active: v5.30 Live Pilot Approval And Provider Activation Execution

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v5.30-ROADMAP.md`
Milestone requirements: `.planning/milestones/v5.30-REQUIREMENTS.md`

Function purpose:

- Convert local pilot contracts into an approved live start or a precise hold decision.
- Capture live/read-only evidence or explicit disablement for payment, notifications, support CRM, BI/APM, mobile/TestFlight, restore, and tabletop dependencies.
- Execute the safe-start gate with live evidence.

Implementation strategy:

- Use `production_pilot_service` gates as the control surface.
- Collect redacted live evidence with owners, timestamps, request/build IDs, blocker states, and rollback controls.
- Keep real users blocked unless the live gate says `start_limited_pilot`.

## Planned: v5.31 Real Limited Pilot Execution Operations

Roadmap: `.planning/milestones/v5.31-ROADMAP.md`
Requirements: `.planning/milestones/v5.31-REQUIREMENTS.md`

Function purpose:

- Enable and operate the approved limited pilot cohort.
- Measure real activation, first learning action, support load, AI quality, mobile stability, billing/account friction, and satisfaction.
- Produce live outcome evidence before any expansion.

Implementation strategy:

- Start only if v5.30 returns `start_limited_pilot`.
- Keep cohort narrow, flags staged, and rollback immediate.
- Run daily launch-room review and support triage.

## Planned: v5.32 Live Pilot Remediation And Reliability Fixes

Roadmap: `.planning/milestones/v5.32-ROADMAP.md`
Requirements: `.planning/milestones/v5.32-REQUIREMENTS.md`

Function purpose:

- Fix the highest-impact issues from live pilot evidence.
- Improve activation, learning quality, support resolution, mobile stability, billing/account trust, and reliability.
- Remove expansion blockers before cohort growth.

Implementation strategy:

- Prioritize live severity, frequency, and learning/support impact.
- Add regression coverage and release evidence for every high-severity issue.
- Keep fixes focused on pilot evidence.

## Planned: v5.33 Controlled Expansion Execution And Revenue Validation

Roadmap: `.planning/milestones/v5.33-ROADMAP.md`
Requirements: `.planning/milestones/v5.33-REQUIREMENTS.md`

Function purpose:

- Expand to a larger controlled cohort only after live remediation evidence supports it.
- Validate revenue, support staffing, teacher operations, mobile/provider capacity, and operational scale under real use.

Implementation strategy:

- Expand gradually with rollback thresholds.
- Treat billing, support staffing, teacher queue load, mobile stability, provider capacity, and BI/APM as scale gates.
- Decide public-launch-prep, hold, remediate, or rollback.

## Planned: v5.34 Public Launch Execution And Post-Launch Operations

Roadmap: `.planning/milestones/v5.34-ROADMAP.md`
Requirements: `.planning/milestones/v5.34-REQUIREMENTS.md`

Function purpose:

- Execute public launch only if final approval exists, or continue controlled expansion/hold.
- Operate post-launch support, incident response, revenue reconciliation, AI/curriculum quality, mobile stability, and growth feedback.

Implementation strategy:

- Start only if v5.33 supports public-launch preparation and final approval is granted.
- Use staged rollout with freeze, rollback, support staffing, provider readiness, and dashboard ownership.
- Close with launch outcome report and v5.35 recommendation.

## Ordering Rationale

1. v5.30 comes first because local contracts are not live approval; real users remain blocked until live evidence clears the gate.
2. v5.31 follows only after `start_limited_pilot` because outcome evidence must come from real controlled use.
3. v5.32 follows because live pilot issues must be fixed before growth.
4. v5.33 follows because expansion must validate revenue, support, mobile, provider, and operational scale before public launch.
5. v5.34 follows because public launch execution should be the result of live expansion evidence and final approval, not readiness optimism.
