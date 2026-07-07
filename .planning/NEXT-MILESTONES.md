# Next Product Milestones

**Updated:** 2026-07-07 after reconciling v5.24 conditional pilot readiness with current activation blockers
**Mode:** post-v5.24 pilot activation, execution, remediation, expansion, and public-launch readiness

## Current Reality

Completed baseline:

- v5.19 completed native mobile source readiness.
- v5.20-v5.23 completed local contracts for native distribution, AI operations, customer lifecycle, and enterprise hardening.
- v5.24 completed limited production pilot and launch readiness as `limited-pilot-ready-local-contracts`.

Important reality check:

- v5.24 did not approve broad public launch.
- v5.24 recommends conditional limited pilot only after activation blockers are cleared or explicitly disabled.
- Remaining real-user blockers include payment, notification, support CRM, BI/APM, mobile store/TestFlight, production restore, and live tabletop activation.

## Active: v5.25 Pilot Activation Blocker Burn-Down And Safe Start Decision

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v5.25-ROADMAP.md`
Milestone requirements: `.planning/milestones/v5.25-REQUIREMENTS.md`

Function purpose:

- Clear, explicitly disable, or launch-block every dependency required for the first real pilot.
- Convert v5.24's conditional go/no-go into a concrete start/hold/harden decision.
- Prepare dry-run accounts, launch-room rehearsal, and safe-start package.

Implementation strategy:

- Start with blocker reality audit across payment, notifications, support CRM, BI/APM, mobile release, restore/tabletop, staffing, cohort, and rollback.
- Use approved live/read-only evidence where possible.
- Explicitly disable non-required dependencies with clear user/support impact.
- Do not enable real users until required blockers are resolved.

## Planned: v5.26 Limited Pilot Execution And Outcome Evidence

Roadmap: `.planning/milestones/v5.26-ROADMAP.md`
Requirements: `.planning/milestones/v5.26-REQUIREMENTS.md`

Function purpose:

- Run the approved pilot cohort under controlled rollout.
- Measure activation, first learning action, usage, support, AI quality, mobile stability, billing/account friction, and satisfaction.
- Decide continue, pause, rollback, remediate, or expansion candidate.

Implementation strategy:

- Start only if v5.25 safe-start gate says `start`.
- Operate daily launch-room monitoring and support triage.
- Collect feedback and metrics as product evidence.
- Block expansion until high-severity pilot issues are handled.

## Planned: v5.27 Pilot Remediation Product Fit And Reliability Hardening

Roadmap: `.planning/milestones/v5.27-ROADMAP.md`
Requirements: `.planning/milestones/v5.27-REQUIREMENTS.md`

Function purpose:

- Convert v5.26 pilot evidence into focused fixes.
- Improve activation, learning quality, support resolution, mobile stability, AI/curriculum relevance, and reliability.
- Prove expansion blockers are resolved or explicitly accepted.

Implementation strategy:

- Prioritize by severity, frequency, and impact on learning/retention.
- Add regression coverage for every high-severity pilot issue.
- Keep changes tied to real pilot evidence rather than speculative polish.
- Do not expand if must-fix blockers remain.

## Planned: v5.28 Controlled Expansion Revenue And Operations Scale

Roadmap: `.planning/milestones/v5.28-ROADMAP.md`
Requirements: `.planning/milestones/v5.28-REQUIREMENTS.md`

Function purpose:

- Expand from narrow pilot to larger controlled cohort.
- Validate revenue operations, support/teacher capacity, mobile/provider readiness, and operational scale.
- Decide whether STOA can prepare for public-launch readiness.

Implementation strategy:

- Expand only if v5.27 clears expansion blockers.
- Increase cohort size gradually with rollback thresholds.
- Treat billing, support staffing, teacher queue load, mobile stability, provider capacity, and BI/APM as scale gates.

## Planned: v5.29 Public Launch Readiness Growth And Self-Serve Onboarding

Roadmap: `.planning/milestones/v5.29-ROADMAP.md`
Requirements: `.planning/milestones/v5.29-REQUIREMENTS.md`

Function purpose:

- Prepare self-serve onboarding, pricing/package readiness, growth/lifecycle loops, public support operations, app-store readiness, and final public launch controls.
- Decide public launch, continued controlled expansion, hold, or harden further.

Implementation strategy:

- Start only if v5.28 expansion evidence supports broader launch preparation.
- Build self-serve signup/subscription/onboarding with support fallback.
- Keep public launch behind final go/no-go, provider capacity, rollback, and support gates.

## Ordering Rationale

1. v5.25 comes first because v5.24 is conditional; unresolved activation blockers make direct pilot execution unsafe.
2. v5.26 follows only after safe-start approval because real pilot evidence is needed before any expansion.
3. v5.27 follows because pilot evidence should drive remediation before cohort growth.
4. v5.28 follows because operational and revenue scale should be tested in controlled expansion before public launch prep.
5. v5.29 follows because self-serve/growth/public launch readiness should come only after controlled expansion shows the product can sustain broader usage.
