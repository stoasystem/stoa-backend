# Next Product Milestones

**Updated:** 2026-07-06 after completing v5.19 native mobile source readiness
**Mode:** plan the next five post-v5.19 product milestones

## Planning Assumption

v5.19 Native Mobile Push And Offline Client Implementation is complete as `native-mobile-source-ready-local` and is not counted in this next-five queue. v5.20 starts from source-ready mobile contracts, not installable device readiness.

## Current Reality After v5.19 Completion

Completed or assumed-complete baseline:

- v5.12 implemented curriculum editor/content migration with special backend authorization, not broad teacher edit rights.
- v5.13 completed local payment/entitlement production readiness.
- v5.15 completed usage/quota/product stability.
- v5.16 completed end-to-end local product readiness and release evidence.
- v5.17 completed external provider activation smoke and release operations.
- v5.18 completed local BI observability contracts for aggregate exports, dashboards, and alert routing.
- v5.19 completed native mobile source implementation, auth/session, student/parent journeys, push/deep links, offline/read-through contracts, and release evidence.

Remaining product gaps:

- Native build distribution, device QA, app credentials, crash/performance telemetry, and store-readiness evidence remain unbuilt after v5.19 source implementation.
- AI teacher tools exist in reviewed/bounded form, but broader quality evaluation, provider cost/latency observability, safety escalation, and autonomy boundaries are not yet complete.
- Support handoff, CRM messaging gates, notification preferences, billing/account operations, and learning-progress signals exist in pieces, but customer lifecycle messaging is not yet an end-to-end product workflow.
- DR, restore drills, SLO/incident operations, credential rotation evidence, and enterprise hardening remain the final stability layer before broader launch pressure.
- A limited production pilot or public launch decision still needs scope, cohort, release control, support staffing, rollback, monitoring, and acceptance criteria.

## Planned: v5.20 Native Build Distribution And Device QA

Roadmap: `.planning/milestones/v5.20-ROADMAP.md`
Requirements: `.planning/milestones/v5.20-REQUIREMENTS.md`

Function purpose:

- Convert the v5.19 mobile implementation into installable internal builds on real iOS/Android devices.
- Prove physical-device auth, parent/student journeys, push/deep-link behavior, offline stale states, and sign-out cleanup.
- Prepare store-readiness artifacts without claiming public launch.

Implementation strategy:

- Add EAS/build profiles, versioning, release channels, internal distribution, and build artifact evidence.
- Run a focused device QA matrix before broader store work.
- Feed mobile crash/performance/release-health signals into existing observability boundaries.

## Planned: v5.21 AI Teaching Quality Cost And Safety Operations

Roadmap: `.planning/milestones/v5.21-ROADMAP.md`
Requirements: `.planning/milestones/v5.21-REQUIREMENTS.md`

Function purpose:

- Make AI summaries, draft explanations, practice generation, and assignment suggestions measurable and controllable.
- Preserve teacher oversight while adding quality rubrics, regression fixtures, provider cost/latency observability, and safety escalation.
- Keep fully autonomous tutoring blocked unless explicit criteria and release evidence exist.

Implementation strategy:

- Audit every AI workflow and classify autonomy level.
- Add golden fixtures and scoring rubrics before expanding behavior.
- Add support-safe cost/latency/provider/fallback summaries.
- Integrate safety/refusal states with teacher review and support workflows.

## Planned: v5.22 Support CRM Customer Messaging And Lifecycle Automation

Roadmap: `.planning/milestones/v5.22-ROADMAP.md`
Requirements: `.planning/milestones/v5.22-REQUIREMENTS.md`

Function purpose:

- Connect support handoff, CRM messaging, notification preferences, account operations, billing, learning progress, and AI/teacher state into governed customer lifecycle workflows.
- Make onboarding, verification, payment, quota, support, progress, and re-engagement messaging usable for parents and operators.

Implementation strategy:

- Define a message taxonomy with event, audience, template, channel, provider gate, preference gate, idempotency key, and support-safe payload.
- Add idempotent lifecycle jobs and admin/parent visibility.
- Keep external writes gated by approved provider credentials, destination policy, templates, and rollout flags.

## Planned: v5.23 Enterprise Stability Compliance And Disaster Recovery Hardening

Roadmap: `.planning/milestones/v5.23-ROADMAP.md`
Requirements: `.planning/milestones/v5.23-REQUIREMENTS.md`

Function purpose:

- Harden STOA's operational foundation after the main product surfaces are connected.
- Prove backup/restore, SLO/incident, rollback, access/credential, audit retention, legal-hold, and compliance evidence workflows.

Implementation strategy:

- Start with an ops risk register across API/Lambda, DynamoDB, S3, Cognito, SES, Bedrock, notifications, support providers, BI/APM, frontend, mobile, queues, and schedules.
- Prioritize safe restore/readback drills and incident/rollback runbooks over broad theoretical compliance work.
- Keep evidence metadata-only and classify live-ready/read-only/local-only/blocked honestly.

## Planned: v5.24 Limited Production Pilot And Launch Readiness

Roadmap: `.planning/milestones/v5.24-ROADMAP.md`
Requirements: `.planning/milestones/v5.24-REQUIREMENTS.md`

Function purpose:

- Decide and prepare the narrowest credible production pilot or launch path after mobile, AI operations, lifecycle messaging, and hardening gates are complete.
- Convert internal readiness into a controlled cohort plan with onboarding, monitoring, support staffing, rollout/rollback, acceptance criteria, and launch decision evidence.

Implementation strategy:

- Start with a launch/pilot readiness audit rather than assuming public release is appropriate.
- Define cohort, scope, success metrics, excluded features, staffing, communication, support hours, and incident ownership.
- Run a final production readiness gate across backend, frontend, mobile, providers, data, support, billing, AI, and observability.
- Close with a go/no-go decision, pilot runbook, rollout plan, rollback plan, and post-pilot learning loop.

## Ordering Rationale

1. v5.20 follows assumed-complete v5.19 because source implementation is not the same as installable device readiness; native push and offline behavior must be proven on devices.
2. v5.21 follows because AI tools already exist, but quality/cost/safety/autonomy controls are the next product-risk bottleneck before broader use.
3. v5.22 follows because customer lifecycle messaging should use stable mobile, AI, support, billing, and account-state signals rather than fragmented manual operations.
4. v5.23 follows because once customer-visible surfaces are connected, restore, SLO, incident, access, credential, and compliance hardening becomes the launch-limiting risk.
5. v5.24 follows because launch/pilot planning should happen only after the core product, mobile delivery, AI controls, lifecycle operations, and hardening gates are credible.
