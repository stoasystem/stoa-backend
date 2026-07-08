# Milestones

## v6.2 Paid Conversion Usage And Account Reliability Completion (Shipped: 2026-07-08)

**Phases completed:** 5 phases, 5 plans, 0 tasks

**Key accomplishments:**

- Added paid conversion completion contracts for package, checkout, payment method, paywall, entitlement activation, renewal, cancellation, failed payment, invoice, and refund.
- Added usage ledger and quota reliability contracts covering pilot-critical learning actions, quota display/blocking, and reconciliation categories.
- Added verification lifecycle and account recovery contracts with support-visible status and private-material-safe evidence keys.
- Added billing support and lifecycle messaging contracts with explicit support capacity gating.
- Added `v6_2_revenue_reliability_gate`, which allows v6.3 only when account and revenue risks are controlled.

---

## v6.1 First Cohort Product Remediation Sprint (Shipped: 2026-07-08)

**Phases completed:** 5 phases, 5 plans, 0 tasks

**Key accomplishments:**

- Added blocker-board/day-one cohort review contracts for v6.0 hold or start outcomes.
- Added account/login/verification/role remediation contracts with safe support-visible copy.
- Added entitlement, usage, notification, support, and teacher-dispatch remediation contracts.
- Added first-learning-action and mobile friction contracts while preserving AI autonomy and curriculum permission boundaries.
- Added `v6_1_remediation_release_gate`, which allows v6.2 only when remediation risks are controlled.

---

## v6.0 Real Evidence Capture And Pilot Start Execution (Shipped: 2026-07-08)

**Phases completed:** 5 phases, 5 plans, 0 tasks

**Key accomplishments:**

- Added v6 real evidence inventory contracts for admin, parent, student, teacher/support, provider, mobile, monitoring, and deployment access paths.
- Added account/payment/usage verification smoke contracts covering login, verification, entitlement, checkout/paywall, usage ledger, quota, and admin support explanations.
- Added notification/support/mobile/provider evidence contracts with explicit pilot disablement, fallback, rollback, and support-copy handling.
- Added first-cohort launch packet and dry-run readiness contracts.
- Added `v6_pilot_start_or_blocker_decision_gate`, which defaults to `hold` and allows v6.1 only on `start_limited_pilot`.

---

## Completed: v5.17 External Provider Activation Smoke And Release Operations

**Status:** Completed local release gate 2026-07-05
**Started:** 2026-07-05
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.17-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.17-REQUIREMENTS.md`
**Goal:** Convert external activation blockers into approved, bounded release operations for provider readiness, safe smoke, refusal evidence, rollback controls, and production read-only verification.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `external-provider-release-ops-ready`

Function purpose:

- Make payment, Cognito/email, notification, support-provider, and production smoke activation state explicit.
- Provide safe live/readiness/safe-fixture smoke paths without exposing secrets or raw provider payloads.
- Preserve fail-closed blocked states when credentials or approvals are unavailable.

Implementation strategy:

- Audit provider readiness surfaces before implementation.
- Use rollout flags and explicit approvals for any live mutation.
- Prefer read-only readiness and safe-fixture smoke over customer-impacting actions.
- Close with honest live-passed/read-only-passed/safe-fixture-passed/blocked evidence.

Planned phases:

- Phase 257: Provider Activation Reality Audit And Release Contract. (complete)
- Phase 258: Payment And Cognito Email Smoke Operations. (complete)
- Phase 259: Notification And Support Provider Smoke Operations. (complete)
- Phase 260: Production Deploy Readiness And Read-Only Browser Smoke. (complete)
- Phase 261: v5.17 External Provider Release Gate. (complete)

Key accomplishments:

- Added admin-only external activation smoke reports for payment/auth, notification/support, and production readiness.
- Preserved no-mutation defaults and deterministic blocked/read-only states for missing credentials, approvals, safe fixtures, and production smoke evidence.
- Documented provider activation blockers, rollback/disable controls, and production read-only smoke runbook.
- Verified focused backend release-gate tests and lint.

---

## Completed: v5.18 Warehouse BI Observability And Product Analytics Activation

**Status:** Completed local release gate 2026-07-05
**Started:** 2026-07-05
**Roadmap:** `.planning/milestones/v5.18-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.18-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.18-MILESTONE-AUDIT.md`
**Goal:** Activate aggregate analytics, BI dashboards, APM/alerting, and operator runbooks after product semantics and provider states are explicit.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `bi-observability-ready-local`

Function purpose:

- Give operators usage, billing readiness, curriculum, teacher help, notification, support, and release-smoke analytics.
- Keep analytics support-safe and separate provider blockers from product regressions.

Completed phases:

- Phase 262: Analytics Reality Audit And Taxonomy Contract. (complete)
- Phase 263: Warehouse Export Job Activation And Schema Evidence. (complete)
- Phase 264: Operator Analytics Dashboard APIs. (complete)
- Phase 265: APM Alert Routing And Observability Runbooks. (complete)
- Phase 266: v5.18 BI Observability Release Gate. (complete)

Key accomplishments:

- Added admin-only BI taxonomy, warehouse readiness/export, dashboard, and alert-routing routes.
- Composed existing usage, billing/provider readiness, curriculum analytics, notification delivery, support SLA, core smoke, and external activation smoke into aggregate support-safe contracts.
- Added fail-closed live BI/APM config flags and blocked states.
- Verified focused BI/source tests, wider BI-composed backend tests, and Ruff.

---

## Completed: v5.19 Native Mobile Push And Offline Client Implementation

**Status:** Completed local release gate 2026-07-06
**Started:** 2026-07-06
**Roadmap:** `.planning/milestones/v5.19-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.19-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.19-MILESTONE-AUDIT.md`
**Goal:** Move native/mobile work from handoff contracts into implementation: app shell, auth/session, parent/student journeys, push, offline/read-through, localization, and release evidence.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 7/7 complete
**Release state:** `native-mobile-source-ready-local`

Function purpose:

- Build a real mobile client against stable backend/web product contracts.
- Implement native push and mobile offline/read-through behavior without demo fallback.

Completed phases:

- Phase 267: Native Mobile Stack And App Shell Contract. (complete)
- Phase 268: Auth Session And Account State. (complete)
- Phase 269: Student And Parent Core Mobile Journeys. (complete)
- Phase 270: Native Push Deep Links And Offline Read-Through. (complete)
- Phase 271: v5.19 Native Mobile Release Gate. (complete)

Key accomplishments:

- Added Expo SDK 57 / React Native 0.86 source workspace under `mobile/`.
- Added app shell, route boundaries, environment/no-demo-fallback contract, and mobile docs.
- Added Amplify/Cognito auth/session wrappers, authenticated API client, support-safe account states, and sign-out cleanup hooks.
- Added student and parent journey adapters against real backend endpoints.
- Added Expo push contracts, backend push-token registration/revocation adapters, notification deep-link validation, and read-through cache privacy guards.
- Verified focused mobile tests with `pytest tests/mobile` passing 26/26 locally.
- Recorded remaining native dependency install, EAS, physical-device QA, FCM/APNs, and app-store blockers.

---

## Completed: v5.20 Native Build Distribution And Device QA

**Status:** Completed local release gate 2026-07-06
**Started:** 2026-07-06
**Roadmap:** `.planning/milestones/v5.20-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.20-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.20-MILESTONE-AUDIT.md`
**Goal:** Turn the native mobile implementation into internal iOS/Android builds with device QA, push/deep-link smoke, crash/performance telemetry, and store-readiness evidence.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `native-distribution-ready-local-contracts`

Function purpose:

- Make the mobile app installable and testable on real devices.
- Prove auth, parent/student journeys, push/deep links, offline stale states, and sign-out cleanup outside the simulator.
- Prepare release-channel, rollback, and app-store prerequisites without claiming public launch.

Implementation strategy:

- Add EAS/internal build profiles after v5.19 app contracts are stable.
- Run a small iOS/Android device QA matrix.
- Feed mobile release health into support-safe observability.
- Close with build IDs, device evidence, and explicit credential/store blockers.

Planned phases:

- Phase 272: Native Build And Credential Readiness Audit. (complete)
- Phase 273: Internal Build Distribution Pipeline. (complete)
- Phase 274: Device QA Matrix And Mobile Smoke. (complete)
- Phase 275: Mobile Crash Performance And Release Telemetry. (complete)
- Phase 276: v5.20 Native Distribution Release Gate. (complete)

---

## Completed: v5.21 AI Teaching Quality Cost And Safety Operations

**Status:** Completed local release gate 2026-07-06
**Started:** 2026-07-06
**Roadmap:** `.planning/milestones/v5.21-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.21-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.21-MILESTONE-AUDIT.md`
**Goal:** Make AI teacher tools measurable, controllable, support-visible, and safe before expanding autonomy.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `ai-operations-ready-local-contracts`

Function purpose:

- Add quality rubrics and regression fixtures for summaries, explanations, exercises, and assignment suggestions.
- Add provider cost/latency/failure/fallback observability.
- Preserve teacher oversight and explicit safety escalation.

Implementation strategy:

- Audit every AI workflow before changing behavior.
- Classify autonomy level for each AI surface.
- Keep review-before-use as the default unless approval/evidence exists.
- Close with AI eval, cost, safety, and teacher-review evidence.

Planned phases:

- Phase 277: AI Workflow Reality Audit And Autonomy Boundary. (complete)
- Phase 278: AI Quality Rubrics And Regression Fixtures. (complete)
- Phase 279: AI Cost Latency Provider Observability. (complete)
- Phase 280: AI Safety Escalation And Teacher Oversight. (complete)
- Phase 281: v5.21 AI Operations Release Gate. (complete)

---

## Completed: v5.22 Support CRM Customer Messaging And Lifecycle Automation

**Status:** Completed local release gate 2026-07-06
**Started:** 2026-07-06
**Roadmap:** `.planning/milestones/v5.22-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.22-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.22-MILESTONE-AUDIT.md`
**Goal:** Connect support handoff, CRM messaging, notifications, account operations, billing, learning progress, and AI/teacher state into governed customer lifecycle workflows.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `customer-lifecycle-ready-local-contracts`

Function purpose:

- Make onboarding, verification, payment, quota, support, progress, and re-engagement messages usable for parents and operators.
- Make support/CRM messaging visible and retryable without exposing private learning content.

Implementation strategy:

- Define lifecycle message taxonomy before adding jobs.
- Use idempotent jobs, approved templates, preference gates, opt-out handling, and provider approval checks.
- Add parent/admin message visibility and support-safe provider-state evidence.

Planned phases:

- Phase 282: Customer Lifecycle Reality Audit And Message Taxonomy. (complete)
- Phase 283: Lifecycle Messaging Orchestrator. (complete)
- Phase 284: Parent And Admin Messaging Surfaces. (complete)
- Phase 285: Support CRM Provider Activation Smoke. (complete)
- Phase 286: v5.22 Customer Lifecycle Release Gate. (complete)

---

## Completed: v5.23 Enterprise Stability Compliance And Disaster Recovery Hardening

**Status:** Completed local release gate 2026-07-06
**Started:** 2026-07-06
**Roadmap:** `.planning/milestones/v5.23-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.23-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.23-MILESTONE-AUDIT.md`
**Goal:** Harden backup/restore, SLOs, incident response, rollback, access/credential operations, audit retention, legal hold, and release controls.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `enterprise-hardening-ready-local-contracts`

Function purpose:

- Reduce launch risk after the main product surfaces are connected.
- Prove restore/readback, incident, rollback, access, credential, and compliance evidence paths.

Implementation strategy:

- Start with an ops risk register across all critical services and providers.
- Prefer safe restore/readback drills and runbook drills over theoretical policy work.
- Keep evidence metadata-only and classify blocked/live/read-only/local states honestly.

Planned phases:

- Phase 287: Ops Stability Reality Audit And Risk Register. (complete)
- Phase 288: Backup Restore And Data Lifecycle Drills. (complete)
- Phase 289: Incident Response SLO And Rollback Operations. (complete)
- Phase 290: Access Secret Rotation And Compliance Evidence. (complete)
- Phase 291: v5.23 Enterprise Hardening Release Gate. (complete)

---

## Completed: v5.24 Limited Production Pilot And Launch Readiness

**Status:** Completed local release gate 2026-07-06
**Started:** 2026-07-06
**Roadmap:** `.planning/milestones/v5.24-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.24-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.24-MILESTONE-AUDIT.md`
**Goal:** Convert internal readiness into a controlled pilot or launch decision with cohort, onboarding, monitoring, support, rollback, acceptance metrics, and go/no-go evidence.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `limited-pilot-ready-local-contracts`

Function purpose:

- Decide the narrowest credible production pilot or launch path after mobile, AI operations, lifecycle messaging, and hardening gates are complete.
- Make rollout scope, cohort, support coverage, monitoring, rollback, success metrics, and feedback loops explicit.
- Avoid an endless internal-development loop by forcing a concrete go/no-go decision.

Implementation strategy:

- Start with a launch/pilot readiness audit instead of assuming public release is appropriate.
- Define one narrow cohort, one narrow product scope, and explicit excluded features.
- Use staged rollout flags, launch-room monitoring, support escalation, and rollback.
- Close with a pilot runbook, launch checklist, go/no-go evidence, and post-pilot learning plan.

Planned phases:

- Phase 292: Launch Scope And Readiness Audit. (complete)
- Phase 293: Pilot Cohort Onboarding And Consent Operations. (complete)
- Phase 294: Production Launch Controls And Monitoring. (complete)
- Phase 295: Pilot Acceptance Metrics And Feedback Loop. (complete)
- Phase 296: v5.24 Launch Readiness Gate. (complete)

---

## Completed: v5.25 Pilot Activation Blocker Burn-Down And Safe Start Decision

**Status:** Complete
**Started:** 2026-07-07
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.25-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.25-REQUIREMENTS.md`
**Goal:** Clear, explicitly disable, or launch-block every dependency required for the first real pilot.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `pilot-safe-start-contracts`

Function purpose:

- Convert v5.24's conditional go/no-go into a concrete start/hold/harden decision.
- Prepare dry-run accounts, launch-room rehearsal, and a safe-start package.

Implementation strategy:

- Audit payment, notifications, support CRM, BI/APM, mobile release, restore/tabletop, staffing, cohort, and rollback.
- Use approved live/read-only evidence where possible.
- Explicitly disable non-required dependencies with clear user/support impact.
- Do not enable real users until required blockers are resolved.

Planned phases:

- Phase 297: Pilot Activation Blocker Reality Audit. (complete)
- Phase 298: Provider Activation Or Explicit Disablement. (complete)
- Phase 299: Pilot Environment Cohort And Account Dry Run. (complete)
- Phase 300: Launch Room Rehearsal And Safe Start Package. (complete)
- Phase 301: Pilot Safe Start Gate. (complete)

---

## Contract Complete: v5.26 Limited Pilot Execution And Outcome Evidence

**Status:** Contract Complete
**Roadmap:** `.planning/milestones/v5.26-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.26-REQUIREMENTS.md`
**Goal:** Run the approved pilot cohort under controlled rollout, daily monitoring, support coverage, feedback capture, and outcome evidence.
**Phases:** 5

Function purpose:

- Move from launch readiness contracts into real pilot operation.
- Measure whether parents/students can activate, use, get help, and keep using STOA under controlled conditions.

Implementation strategy:

- Start only if v5.25 safe-start gate says `start`.
- Keep cohort narrow and feature flags staged.
- Use daily operational review and support triage.

Planned phases:

- Phase 302: Pilot Cohort Enablement And First-Use Tracking. (contract complete)
- Phase 303: Daily Pilot Monitoring And Incident Operations. (contract complete)
- Phase 304: Pilot Support Feedback And Learning Quality Evidence. (contract complete)
- Phase 305: Pilot Metrics Outcome Analysis. (contract complete)
- Phase 306: Pilot Outcome Decision Gate. (contract complete)

---

## Contract Complete: v5.27 Pilot Remediation Product Fit And Reliability Hardening

**Status:** Contract Complete
**Roadmap:** `.planning/milestones/v5.27-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.27-REQUIREMENTS.md`
**Goal:** Turn v5.26 pilot evidence into focused product, reliability, support, AI, curriculum, and mobile fixes before any expansion.
**Phases:** 5

Function purpose:

- Fix the issues actual pilot users hit.
- Improve activation, learning usefulness, support resolution, mobile stability, and trust signals.

Implementation strategy:

- Prioritize by pilot severity, frequency, and impact on learning/retention.
- Add regression coverage for high-severity pilot issues.
- Keep remediation tied to pilot evidence.

Planned phases:

- Phase 307: Pilot Issue Triage And Remediation Backlog. (contract complete)
- Phase 308: Account Billing Mobile And Notification Remediation. (contract complete)
- Phase 309: Learning AI Curriculum And Teacher-Help Remediation. (contract complete)
- Phase 310: Pilot Regression And Reliability Evidence. (contract complete)
- Phase 311: Remediation Release Gate. (contract complete)

---

## Contract Complete: v5.28 Controlled Expansion Revenue And Operations Scale

**Status:** Contract Complete
**Roadmap:** `.planning/milestones/v5.28-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.28-REQUIREMENTS.md`
**Goal:** Expand from a narrow pilot to a larger controlled cohort with revenue, support staffing, teacher operations, mobile release, provider capacity, and operational scale controls.
**Phases:** 5

Function purpose:

- Test whether STOA can support more users without losing reliability or support quality.
- Validate billing/revenue operations under controlled real usage.

Implementation strategy:

- Expand only if v5.27 clears expansion blockers.
- Increase cohort size gradually with rollback thresholds.
- Treat billing, support staffing, teacher queue load, mobile stability, provider capacity, and BI/APM as scale gates.

Planned phases:

- Phase 312: Expansion Cohort And Capacity Plan. (contract complete)
- Phase 313: Revenue Billing And Subscription Operations Scale. (contract complete)
- Phase 314: Teacher Support And Customer Operations Scale. (contract complete)
- Phase 315: Mobile Provider And Infrastructure Scale Smoke. (contract complete)
- Phase 316: Controlled Expansion Gate. (contract complete)

---

## Contract Complete: v5.29 Public Launch Readiness Growth And Self-Serve Onboarding

**Status:** Contract Complete
**Roadmap:** `.planning/milestones/v5.29-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.29-REQUIREMENTS.md`
**Goal:** Prepare STOA for public launch or a larger market-facing release through self-serve onboarding, growth loops, pricing/package readiness, public support operations, app-store readiness, and final launch controls.
**Phases:** 5

Function purpose:

- Make the product usable beyond manually managed cohorts.
- Prepare acquisition, onboarding, payment, support, and retention operations for broader traffic.

Implementation strategy:

- Start only if v5.28 expansion evidence supports broader launch preparation.
- Build self-serve account/subscription/onboarding controls with clear support fallback.
- Keep public launch behind final go/no-go, rollback, support, and provider-readiness gates.

Planned phases:

- Phase 317: Self-Serve Onboarding And Account Conversion. (contract complete)
- Phase 318: Pricing Packaging Growth And Lifecycle Readiness. (contract complete)
- Phase 319: Public Support Knowledge Base And Launch Communications. (contract complete)
- Phase 320: App Store Public Release And Production Launch Controls. (contract complete)
- Phase 321: Public Launch Readiness Gate. (contract complete)

---

## Complete: v5.30 Live Pilot Approval And Provider Activation Execution

**Status:** Complete
**Started:** 2026-07-07
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.30-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.30-REQUIREMENTS.md`
**Goal:** Obtain explicit operational approval, clear or disable live activation blockers, and produce live evidence required for `pilot_safe_start_gate` to return `start_limited_pilot`.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete

Function purpose:

- Make the first real pilot decision operationally real, not only locally modeled.
- Keep real-user activation blocked unless the live gate says start.

Implementation strategy:

- Use `production_pilot_service` gates as the control surface.
- Collect redacted live/read-only evidence for each required provider and operational dependency.
- Record user/support impact for intentionally disabled pilot dependencies.

Planned phases:

- Phase 322: Live Approval And Ownership Audit. (complete)
- Phase 323: Live Provider And Mobile Activation Evidence. (complete)
- Phase 324: Production Restore Tabletop And Launch-Room Evidence. (complete)
- Phase 325: Live Pilot Safe-Start Gate Execution. (complete)
- Phase 326: Live Activation Gate. (complete)

---

## Contract Complete: v5.31 Real Limited Pilot Execution Operations

**Status:** Contract Complete
**Roadmap:** `.planning/milestones/v5.31-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.31-REQUIREMENTS.md`
**Goal:** Execute the approved limited pilot cohort with live operational monitoring, support coverage, feedback capture, and daily go/hold/rollback decisions.
**Phases:** 5

Function purpose:

- Validate STOA with real parent/student users under controlled scope.
- Produce real outcome evidence before expansion.

Implementation strategy:

- Start only if v5.30 returns `start_limited_pilot`.
- Keep cohort narrow, flags staged, and rollback immediate.
- Operate daily launch-room review.

Planned phases:

- Phase 327: Live Cohort Enablement And Onboarding Operations. (contract complete)
- Phase 328: Daily Pilot Operations And Incident Review. (contract complete)
- Phase 329: Live Learning Feedback And Support Quality Capture. (contract complete)
- Phase 330: Live Pilot Outcome Analysis. (contract complete)
- Phase 331: Live Pilot Decision Gate. (contract complete)

---

## Contract Complete: v5.32 Live Pilot Remediation And Reliability Fixes

**Status:** Contract Complete
**Roadmap:** `.planning/milestones/v5.32-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.32-REQUIREMENTS.md`
**Goal:** Fix the highest-impact issues from the real limited pilot across activation, mobile, billing, learning quality, AI, support, and reliability before expansion.
**Phases:** 5

Function purpose:

- Turn live user evidence into targeted product improvements.
- Remove expansion blockers discovered during pilot.

Implementation strategy:

- Prioritize live severity, frequency, and learning/support impact.
- Add regression coverage and release evidence for high-severity issues.
- Keep fixes focused on pilot evidence.

Planned phases:

- Phase 332: Live Pilot Issue Triage And Fix Plan. (contract complete)
- Phase 333: Account Mobile Billing Notification Fixes. (contract complete)
- Phase 334: Learning AI Curriculum Teacher-Help Fixes. (contract complete)
- Phase 335: Regression Release And Support Evidence. (contract complete)
- Phase 336: Remediation Gate. (contract complete)

---

## Contract Complete: v5.33 Controlled Expansion Execution And Revenue Validation

**Status:** Contract Complete
**Roadmap:** `.planning/milestones/v5.33-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.33-REQUIREMENTS.md`
**Goal:** Execute controlled cohort expansion and validate revenue, support staffing, teacher operations, mobile/provider capacity, and operational scale under real usage.
**Phases:** 5

Function purpose:

- Test whether STOA can support more users without degrading support quality or learning outcomes.
- Validate billing/revenue and support operations under controlled real load.

Implementation strategy:

- Expand only if v5.32 remediation gate says expansion-ready.
- Increase cohort size gradually with rollback thresholds.
- Treat billing, support, mobile, provider, and BI/APM as scale gates.

Planned phases:

- Phase 337: Live Expansion Cohort And Capacity Enablement. (contract complete)
- Phase 338: Live Revenue Billing And Subscription Validation. (contract complete)
- Phase 339: Live Teacher Support And Customer Operations Scale. (contract complete)
- Phase 340: Live Mobile Provider And Infrastructure Scale Evidence. (contract complete)
- Phase 341: Controlled Expansion Decision Gate. (contract complete)

---

## Contract Complete: v5.34 Public Launch Execution And Post-Launch Operations

**Status:** Contract Complete
**Roadmap:** `.planning/milestones/v5.34-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.34-REQUIREMENTS.md`
**Goal:** Execute a public launch or continue controlled expansion based on final approval, then operate post-launch monitoring, support, revenue, incident response, and learning loops.
**Phases:** 5

Function purpose:

- Move from launch readiness into launch execution only if final approval exists.
- Establish post-launch operating cadence and expansion/hold criteria.

Implementation strategy:

- Start only if v5.33 supports public-launch preparation and final approval is granted.
- Use staged rollout with freeze, rollback, support staffing, and dashboard ownership.
- Close with launch outcome report and v5.35 recommendation.

Planned phases:

- Phase 342: Final Launch Approval And Public Rollout Plan. (contract complete)
- Phase 343: Self-Serve Onboarding Growth And Support Launch. (contract complete)
- Phase 344: App Store Production Release And Launch Monitoring. (contract complete)
- Phase 345: Post-Launch Incident Revenue And Learning Operations. (contract complete)
- Phase 346: Launch Outcome And Next Strategy Gate. (contract complete)

---

## Completed: v5.35 Real Pilot Blocker Burn-Down And Launch Execution

**Status:** Complete locally 2026-07-07; real pilot start remains gated by current evidence
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.35-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.35-REQUIREMENTS.md`
**Goal:** Clear or explicitly disable the real blockers that keep the pilot gate in hold, then execute the live safe-start gate for the first narrow cohort.
**Phases:** 5
**Audit:** `.planning/v5.35-MILESTONE-AUDIT.md`
**Evidence:** `.planning/milestones/v5.35-v5.39-REAL-PILOT-SCALE-SEQUENCE-EVIDENCE.md`

Function purpose:

- Turn v5.30-v5.34 metadata-only contracts into an executable internal pilot start decision.
- Keep public launch, paid marketing, broad expansion, and uncontrolled provider writes blocked.

Implementation strategy:

- Reconcile the blocker inventory first.
- Activate providers where approved, otherwise document pilot disablement, fallback, copy, and support path.
- Run the live safe-start gate before enabling any real cohort.

Completed phases:

- Phase 347: Live Blocker Inventory And Owner Assignment. (complete)
- Phase 348: Provider Or Disablement Activation Closeout. (complete)
- Phase 349: Pilot Cohort Account And Support Dry Run. (complete)
- Phase 350: Launch Room Restore And Incident Readiness Closeout. (complete)
- Phase 351: Real Pilot Start Decision Gate. (complete)

---

## Contract Complete: v5.36 Live Pilot Operations Feedback And Product Fixes

**Status:** Contract complete locally 2026-07-07; real operations gated by v5.35 start
**Roadmap:** `.planning/milestones/v5.36-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.36-REQUIREMENTS.md`
**Goal:** Operate the first approved cohort, collect real product/support/learning evidence, and ship the highest-impact fixes before expansion.
**Phases:** 5

Function purpose:

- Replace readiness assumptions with real activation, support, billing, mobile, AI, teacher, and learning evidence.
- Convert pilot issues into focused fixes and a clear expand/hold/rollback/remediate decision.

Implementation strategy:

- Start only if v5.35 returns `start_limited_pilot`.
- Run daily pilot review and ship high-impact fixes with focused tests and support-visible release notes.

Contract-complete phases:

- Phase 352: First Cohort Live Operations. (contract complete)
- Phase 353: Daily Feedback Incident And Metrics Review. (contract complete)
- Phase 354: High-Impact Pilot Fix Implementation. (contract complete)
- Phase 355: Pilot Learning Outcome And Support Quality Review. (contract complete)
- Phase 356: Pilot Outcome Decision Gate. (contract complete)

---

## Contract Complete: v5.37 Revenue Conversion And Self-Serve Growth Completion

**Status:** Contract complete locally 2026-07-07; controlled growth gated by revenue and support evidence
**Roadmap:** `.planning/milestones/v5.37-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.37-REQUIREMENTS.md`
**Goal:** Complete parent-facing paid conversion, entitlement reconciliation, lifecycle messaging, and controlled growth loops from real pilot evidence.
**Phases:** 5

Function purpose:

- Make checkout, subscription state, quota/usage explanations, billing support, and retention messaging dependable for real customers.
- Keep growth capacity-aware and support-visible.

Implementation strategy:

- Prioritize from pilot conversion friction and support tickets.
- Reconcile provider, entitlement, usage ledger, invoice/refund, and admin support states.

Contract-complete phases:

- Phase 357: Pricing Package And Checkout Reality Closeout. (contract complete)
- Phase 358: Entitlement Revenue And Usage Reconciliation. (contract complete)
- Phase 359: Lifecycle Messaging And Retention Loop Completion. (contract complete)
- Phase 360: Referral Waitlist And Controlled Growth Surface. (contract complete)
- Phase 361: Revenue Growth Readiness Gate. (contract complete)

---

## Contract Complete: v5.38 Learning Outcomes Curriculum And AI Quality Scale

**Status:** Contract complete locally 2026-07-07; learning scale gated by outcome and AI quality evidence
**Roadmap:** `.planning/milestones/v5.38-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.38-REQUIREMENTS.md`
**Goal:** Improve curriculum, exercise quality, adaptive recommendations, AI teacher tools, summaries, practice generation, and learning outcome reporting.
**Phases:** 5

Function purpose:

- Strengthen the core learning value after real usage.
- Convert pilot learning evidence into content, AI, recommendation, and teacher-review improvements.

Implementation strategy:

- Use pilot evidence, teacher review, curriculum analytics, and support tickets.
- Keep curriculum editing restricted to specially authorized operators and AI automation reviewed or policy-bound.

Contract-complete phases:

- Phase 362: Learning Outcome Evidence And Gap Analysis. (contract complete)
- Phase 363: Curriculum Coverage And Exercise Bank Completion. (contract complete)
- Phase 364: AI Summary Exercise And Teacher Tool Quality Improvements. (contract complete)
- Phase 365: Adaptive Recommendation And Assignment Quality Loop. (contract complete)
- Phase 366: Learning Quality Scale Gate. (contract complete)

---

## Contract Complete: v5.39 Platform Reliability And Internal Operations Scale

**Status:** Contract complete locally 2026-07-07; larger expansion gated by operations evidence
**Roadmap:** `.planning/milestones/v5.39-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.39-REQUIREMENTS.md`
**Goal:** Harden reliability, observability, data quality, admin operations, teacher/support workflows, incident handling, release discipline, and rollback readiness for larger cohorts.
**Phases:** 5

Function purpose:

- Reduce operational drag before more families, teachers, and support staff depend on the system.
- Make internal workflows repeatable and observable.

Implementation strategy:

- Use v5.35-v5.38 operational evidence.
- Prioritize high-frequency admin/support/teacher tasks and measured reliability risks.

Contract-complete phases:

- Phase 367: Reliability Incident And Data Quality Audit. (contract complete)
- Phase 368: Admin Teacher And Support Workflow Scale-Up. (contract complete)
- Phase 369: Observability Dashboard And Alert Tuning. (contract complete)
- Phase 370: Release Rollback And Migration Discipline. (contract complete)
- Phase 371: Operations Scale Readiness Gate. (contract complete)

---

## Planned: v6.3 Learning Outcome And AI Curriculum Quality Sprint

**Status:** Planned
**Roadmap:** `.planning/milestones/v6.3-ROADMAP.md`
**Requirements:** `.planning/milestones/v6.3-REQUIREMENTS.md`
**Goal:** Improve curriculum, exercises, AI teacher tools, adaptive recommendations, parent progress reporting, and learning outcomes from real evidence.
**Phases:** 5

Function purpose:

- Make STOA valuable because students learn, not because operations are merely ready.
- Convert weak-topic, support, teacher, and parent feedback into curriculum and AI quality fixes.

Implementation strategy:

- Prioritize high-frequency learning friction from pilot data.
- Keep curriculum editing specially authorized and AI automation reviewed or policy-bound.

Planned phases:

- Phase 387: Learning Outcome Evidence Review. (planned)
- Phase 388: Curriculum Exercise And Explanation Quality Fixes. (planned)
- Phase 389: AI Teacher Summary And Practice Generation Quality Fixes. (planned)
- Phase 390: Adaptive Recommendation And Parent Progress Clarity. (planned)
- Phase 391: v6.3 Learning Quality Gate. (planned)

---

## Planned: v6.4 Operations Scale Release And Observability Hardening

**Status:** Planned
**Roadmap:** `.planning/milestones/v6.4-ROADMAP.md`
**Requirements:** `.planning/milestones/v6.4-REQUIREMENTS.md`
**Goal:** Harden observability, support/admin/teacher workflows, release discipline, rollback, migration safety, incident handling, and ownership for larger controlled cohorts.
**Phases:** 5

Function purpose:

- Make the system operable by a small team without founder-only manual coordination.
- Catch reliability, billing, notification, support, teacher dispatch, AI/provider, mobile, and release issues before users report them.

Implementation strategy:

- Use v6.0-v6.3 evidence as the risk register.
- Tie dashboards and alerts to owners and runbooks.

Planned phases:

- Phase 392: Operations Risk And Incident Review. (planned)
- Phase 393: Admin Support Teacher Workflow Scale Fixes. (planned)
- Phase 394: Observability Alert And Dashboard Hardening. (planned)
- Phase 395: Release Migration Rollback And Smoke Discipline. (planned)
- Phase 396: v6.4 Controlled Expansion Readiness Gate. (planned)

---

## Completed: v5.16 End-To-End Product Readiness And Release Evidence

**Status:** Completed local release gate 2026-07-05
**Started:** 2026-07-05
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.16-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.16-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.16-MILESTONE-AUDIT.md`
**Goal:** Verify the real product as an end-to-end system and produce release evidence that separates implementation gaps from external provider blockers.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `product-readiness-evidence-local`

Function purpose:

- Prove parent, student, and admin journeys work across auth, verification, billing, entitlement, usage/quota, curriculum, teacher help, and support views.
- Close or precisely classify the residual v5.14 focused frontend e2e blocker.
- Consolidate backend smoke, frontend e2e, and milestone evidence into one release-readiness matrix.

Implementation strategy:

- Audit current backend/frontend reality before adding code.
- Run focused frontend e2e when execution permission is available.
- Add only small contract fixes discovered by end-to-end evidence.
- Keep external provider activation blocked unless credentials and rollout approval are available.

Completed phases:

- Phase 252: Product Readiness Reality Audit And Evidence Contract. (complete)
- Phase 253: Focused Frontend E2E Gate Closure. (complete)
- Phase 254: Backend Product Smoke Evidence Expansion. (complete)
- Phase 255: Cross-Surface Product Journey Verification. (complete)
- Phase 256: v5.16 Release Evidence Gate And Next Milestone Decision. (complete)

Key accomplishments:

- Wrote a product-readiness evidence matrix across auth, verification, billing, entitlement, usage/quota, curriculum, teacher help, account operations, and support views.
- Closed the residual v5.14 focused frontend e2e gate with 24/24 focused Playwright tests passing.
- Verified backend smoke/support evidence with 121 focused tests and Ruff.
- Verified supplemental parent/student/admin journey evidence with 11/11 Playwright tests passing.
- Ran final frontend build and lint successfully.

Known deferred items: live Stripe/TWINT charging and webhook activation, live Cognito/email delivery smoke, notification/support provider activation, BI/warehouse/APM/native activation, and production mutation outside approved safe fixtures.

---

## Completed: v5.12 Curriculum Editor And Content Migration Buildout

**Status:** Completed local release gate 2026-07-05
**Started:** 2026-07-05
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.12-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.12-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.12-MILESTONE-AUDIT.md`
**Goal:** Implement the curriculum editor and production content migration tooling that v5.1 left as readiness/deferred scope.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `curriculum-buildout-ready`

Function purpose:

- Give specially authorized internal curriculum operators a real curriculum authoring workbench.
- Ensure ordinary teachers/tutors cannot edit curriculum unless backend grants them explicit curriculum capabilities.
- Add backend draft patch/update, validation preview, diff, audit-read, migration dry-run/apply, evidence, and rollback metadata support.
- Add a frontend migration console for manifest validation, conflict review, apply confirmation, and evidence review.
- Preserve published student/parent curriculum reads and adaptive assignment behavior.

Implementation strategy:

- Start from the v5.1 readiness audit's deferred items.
- Build backend editor/migration APIs before frontend tooling.
- Keep migration dry-run non-mutating and apply explicitly confirmed.
- Avoid external activation work and broad CMS/collaboration scope during this milestone.
- Prioritize usable internal feature flow over broad unrelated security/compliance testing.

Completed phases:

- Phase 232: Curriculum Buildout Reality Refresh And Contract. (complete)
- Phase 233: Backend Special Authorization Editor Patch Validation Diff And Audit APIs. (complete)
- Phase 234: Backend Content Migration Service And APIs. (complete)
- Phase 235: Frontend Curriculum Editor And Migration Console. (complete)
- Phase 236: v5.12 Curriculum Buildout Release Gate. (complete)

Key accomplishments:

- Added explicit curriculum capabilities for author, reviewer, publisher, and migration operator workflows.
- Added backend draft patch, validation preview, diff, audit-read, migration dry-run/apply, evidence, and rollback metadata.
- Added frontend `/admin/curriculum` worklist, editor, review, migration, and evidence console in `/Users/zhdeng/stoa-frontend`.
- Verified backend focused tests, frontend build/lint/e2e, and no-demo-fallback API-error behavior.

Known deferred items: native apps, live Stripe/TWINT activation, external support provider activation, live notification provider/native push activation, warehouse/BI deployment, broad collaborative CMS, and unreviewed AI publication.

---

## Completed: v5.13 Payment And Entitlement Production Completion

**Status:** Completed local release gate 2026-07-05
**Started:** 2026-07-05
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.13-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.13-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.13-MILESTONE-AUDIT.md`
**Goal:** Make paid access work as a real product flow instead of only local/backend readiness.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `payment-production-ready-local`

Function purpose:

- Complete checkout/paywall state, webhook reconciliation, entitlement activation, usage-limit compatibility, admin billing evidence, and refund/cancellation support state.
- Audit current reality first so prior payment planning evidence is not mistaken for working user-facing behavior.

Implementation strategy:

- Start from provider-backed payment events and reconcile entitlements idempotently.
- Keep manual override visible as a support path, not a substitute for paid access.
- Treat live provider smoke as blocked unless production credentials and rollout approval exist.

Completed phases:

- Phase 237: Payment Reality Audit And Contract Refresh. (complete)
- Phase 238: Checkout Paywall And Paid-State Integration. (complete)
- Phase 239: Webhook Reconciliation And Entitlement Activation. (complete)
- Phase 240: Billing Support Evidence And Lifecycle Edge States. (complete)
- Phase 241: v5.13 Payment Production Completion Gate. (complete)

Key accomplishments:

- Rewired parent-facing billing paid state and checkout creation to canonical parent subscription APIs without paid-state demo fallback.
- Hardened Stripe webhook reconciliation with support-visible duplicate evidence and stale event protection.
- Preserved provider-backed entitlements/profile tiers across duplicate and stale provider deliveries.
- Added bounded billing `supportEvidence` for lifecycle, invoice, refund, dunning, manual override, and reconciliation metadata.
- Surfaced support action and duplicate/stale reconciliation counts in frontend admin billing/account operations views.

Known deferred items: live Stripe/TWINT customer-charging smoke, production deploy/live smoke, production webhook endpoint registration, finance acceptance, and explicit rollout approval.

---

## Historical Partial Gate: v5.14 Verification And Login Reliability

**Status:** Partial local gate at close; residual focused frontend e2e blocker was closed by v5.16 product-readiness evidence
**Started:** 2026-07-05
**Roadmap:** `.planning/milestones/v5.14-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.14-REQUIREMENTS.md`
**Goal:** Make email verification, login-code policy, account activation, resend/confirm, and support recovery reliable.
**Phases:** 5
**Plans:** 4/5 complete
**Requirements:** 4/5 complete
**Release target:** `verification-login-reliable-local`
**Follow-up closure:** v5.16 closed the focused frontend e2e blocker with 24/24 focused Playwright tests passing.

Function purpose:

- Ensure real users can register, verify, log in, recover from common verification failures, and receive clear frontend/support states.
- Remove or complete half-enabled login-code/passwordless behavior.

Implementation strategy:

- Audit Cognito/local profile/frontend behavior before changing policy.
- Prefer one canonical login path over multiple partially working paths.
- Add bounded support visibility and focused rate-limit/abuse controls.

Phase status:

- Phase 242: Verification And Login Reality Audit. (complete)
- Phase 243: Backend Verification Resend Confirm Reliability. (complete)
- Phase 244: Login Code And Passwordless Policy Resolution. (complete)
- Phase 245: Frontend Verification Recovery And Admin Support Visibility. (complete)
- Phase 246: v5.14 Verification Login Reliability Gate. (partial)

---

## Completed: v5.15 Usage, Quota, And Product Stability

**Status:** Completed local release gate 2026-07-05
**Roadmap:** `.planning/milestones/v5.15-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.15-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.15-MILESTONE-AUDIT.md`
**Goal:** Make usage accounting, quota reconciliation, support explanations, and core smoke checks trustworthy.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `usage-stability-ready-local`

Function purpose:

- Ensure real usage events, entitlement limits, and visible quota state agree across student/parent/admin surfaces.
- Add internal health/smoke gates for the flows most likely to break product operation.

Implementation strategy:

- Audit actual flow coverage instead of assuming prior ledger planning is complete.
- Reconcile ledger rows, aggregate counters, entitlement state, and support summaries.
- Keep observability support-safe and focused on request IDs/metadata rather than raw learning content.

Completed phases:

- Phase 247: Usage Flow Reality Audit And Stability Contract. (complete)
- Phase 248: Ledger Coverage And Idempotency Closure. (complete)
- Phase 249: Quota Reconciliation And Support Explanations. (complete)
- Phase 250: Core Health Smoke And Regression Checks. (complete)
- Phase 251: v5.15 Usage Stability Release Gate. (complete)

Key accomplishments:

- Mapped real usage-bearing flows across question submit, chat, hints, teacher help, practice, lesson, assignment, read-only, account operations, and admin usage surfaces.
- Added governed `practice_teacher_help_request` usage ledger coverage and hardened mismatched question idempotency retries.
- Added support-safe reconciliation states and explanations for no-usage, over-limit, stale, drifted, matched, and ledger-only states.
- Added parent/admin account operations usage support action and explanation rendering.
- Added admin `GET /admin/core-smoke` for support-safe local product smoke evidence.

Known deferred items: v5.14 focused frontend e2e blocker, live-provider activation, BI/warehouse, external APM, native apps, and production deploy/live smoke.

---

## v5.10 Account Operations Frontend And Production Readiness (Completed: 2026-07-03)

**Status:** Completed local frontend/readiness release gate 2026-07-03
**Started:** 2026-07-03
**Roadmap:** `.planning/milestones/v5.10-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.10-REQUIREMENTS.md`
**Goal:** Turn completed backend account operations, email verification, entitlement, and usage state into frontend-visible workflows with production read-only readiness.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `frontend-account-ops-ready`

Function purpose:

- Make email verification usable in the frontend instead of backend-only.
- Expose parent account operations state through a parent-facing UI.
- Expose admin account operations detail through a support workflow.
- Prepare production read-only verification for the account operations surface.

Implementation strategy:

- Start with a reality refresh because old final-polish audit docs are stale after v5.6-v5.9 completion.
- Add frontend clients/query keys before pages.
- Keep backend primitive changes limited to contract fixes discovered during frontend integration.
- Prioritize functionality and usable states over broad security/compliance testing during internal development.

Completed phases:

- Phase 222: Reality Refresh And Frontend Account Operations Contract. (complete)
- Phase 223: Email Verification UX Integration.
- Phase 224: Parent Account Operations UI.
- Phase 225: Admin Account Operations Console.
- Phase 226: v5.10 Frontend And Production Readiness Gate.

Phase evidence: `.planning/phases/222-current-reality-refresh-and-frontend-account-ops-contract/`, `.planning/phases/223-email-verification-ux-integration/`, `.planning/phases/224-parent-account-operations-ui/`, `.planning/phases/225-admin-account-operations-console/`, `.planning/phases/226-v5-10-frontend-and-production-readiness-gate/`.

Key accomplishments:

- Added frontend email verification resend/confirm UX and login/register pending-verification states.
- Added parent account operations dashboard entry and `/parent/account-operations`.
- Added admin account operations support console and subscription handoff links.
- Verified frontend lint/build, 15 focused frontend e2e tests, and 35 backend focused contract tests.
- Captured production read-only smoke checklist.

Known deferred items: additional usage ledger coverage for non-question actions, passwordless/login-code custom auth, native app buildout, live Stripe/TWINT activation, external provider activation, and warehouse/BI.

---

## v5.11 Additional Usage Ledger Coverage (Completed: 2026-07-04)

**Status:** Completed local backend release gate 2026-07-04
**Started:** 2026-07-04
**Roadmap:** `.planning/milestones/v5.11-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.11-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.11-MILESTONE-AUDIT.md`
**Goal:** Extend usage ledger coverage beyond question submissions for account operations explanations and paid-limit governance.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 6/6 complete
**Release state:** `multi-action-usage-ledger-ready`

Function purpose:

- Define governed usage action taxonomy for chat, hints, teacher-help, and practice/generation actions.
- Record privacy-safe, idempotent ledger events for eligible successful backend flows.
- Reconcile and summarize multi-action usage without breaking question quota compatibility.
- Keep parent/admin account operations compatible with additive, content-safe usage explanations.

Implementation strategy:

- Define action names, success/skip rules, idempotency, and privacy schema before implementation.
- Preserve existing `question_submission` ledger and counter behavior.
- Instrument existing successful backend flows only; document future-only actions where no route exists.
- Extend summaries and account operations after new ledger events exist.

Phase progress:

- Phase 227: Usage Action Taxonomy And Ledger Contract. (complete)
- Phase 228: Chat And Teacher-Help Ledger Instrumentation. (complete)
- Phase 229: Practice And Generation Ledger Instrumentation. (complete)
- Phase 230: Multi-Action Reconciliation And Account Operations Summaries. (complete)
- Phase 231: v5.11 Privacy Regression And Release Gate. (complete)

Key accomplishments:

- Added governed usage action taxonomy for question, chat, hints, teacher-help, practice, assignments, and reviewed generation.
- Added privacy-safe, idempotent ledger events for chat, teacher-help, hints, practice answers, lesson completion, assignment generation, and assignment lifecycle side effects.
- Added multi-action reconciliation and usage summaries while preserving question quota compatibility.
- Preserved parent/admin account operations compatibility with additive usage details.
- Verified with 72 focused backend tests and Ruff.

Known deferred items: production deploy/live smoke, frontend visual polish for expanded usage summaries, warehouse/BI export, live Stripe/TWINT activation, and cleanup archive movement after archive target verification.

---

## v5.9 Parent Admin Operations Visibility (Completed: 2026-07-03)

**Status:** Completed local backend release gate 2026-07-03
**Started:** 2026-07-03
**Roadmap:** `.planning/milestones/v5.9-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.9-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.9-MILESTONE-AUDIT.md`
**Phase evidence:** `.planning/milestones/v5.9-phases/`
**Goal:** Provide bounded parent/admin operations visibility that composes entitlement, billing, usage, verification, and binding state into support-grade account summaries.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `operations-visible`

Function purpose:

- Give parents one consolidated summary of account operations state.
- Give admins a bounded support-grade parent operations detail.
- Compose v5.6 entitlement, v5.7 usage ledger/reconciliation, and v5.8 verification state without new storage.
- Preserve privacy boundaries by omitting raw learning content, provider payloads, auth tokens, private artifact keys, and verification codes.

Implementation strategy:

- Define the shared operations visibility contract before routes.
- Add a shared account operations aggregation service.
- Expose parent-scoped summary first, then admin detail with bounded event visibility.
- Close with focused regression tests, docs, audit, and archive evidence.

Completed phases:

- Phase 217: Account Operations Visibility Contract.
- Phase 218: Parent Account Operations Summary.
- Phase 219: Admin Parent Operations Detail.
- Phase 220: Privacy Regression Tests And Operations Evidence.
- Phase 221: v5.9 Operations Visibility Release Gate.

Key accomplishments:

- Added `GET /parents/me/account-operations`.
- Added `GET /admin/account-operations/parents/{parent_id}`.
- Added shared `account_operations_service` aggregation for parent profile, billing, child binding, entitlement, usage, verification, and support state.
- Added support-state blocker/warning signals for unverified accounts, inactive billing, missing children, non-active bindings, and unreconciled usage.
- Verified with focused parent/admin account operations tests and targeted Ruff.

Known deferred items at close: frontend/native account operations UI, production deploy/live smoke, broad CRM/customer messaging, analytics warehouse/cross-account search, native apps, final live Stripe/TWINT activation, and actual Cognito custom-auth passwordless login-code support.

---

## v5.8 Email Verification And Login Code Policy (Completed: 2026-07-03)

**Status:** Completed local backend release gate 2026-07-03
**Started:** 2026-07-03
**Roadmap:** `.planning/milestones/v5.8-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.8-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.8-MILESTONE-AUDIT.md`
**Phase evidence:** `.planning/milestones/v5.8-phases/`
**Goal:** Replace placeholder email verification behavior and clarify token-compatible login-code/passwordless policy.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `policy-deferred`

Function purpose:

- Define backend-visible email verification states and route policy.
- Enforce registration/account lifecycle behavior without breaking role onboarding or parent/student binding.
- Add safe verification resend/expiry behavior and bounded support visibility.
- Resolve login-code/passwordless behavior as Cognito-compatible production auth or explicitly gated/deferred behavior.

Implementation strategy:

- Define state and route policy before enforcement changes.
- Preserve current Cognito login, forgot-password, role onboarding, and parent/student binding behavior.
- Keep raw verification codes and provider secrets out of DynamoDB.
- Close with focused auth lifecycle tests and release evidence before v5.9 operations visibility.

Completed phases:

- Phase 212: Email Verification Contract And Account State Policy.
- Phase 213: Registration Verification Enforcement.
- Phase 214: Verification Resend And Expiry Operations.
- Phase 215: Login Code Policy And Auth Lifecycle Tests.
- Phase 216: v5.8 Verification Release Gate.

Key accomplishments:

- Replaced backend-admin-marked verification for new registrations with Cognito `sign_up` and `confirm_sign_up` lifecycle.
- Added explicit verification state, activation status, and public response fields.
- Blocked registration/login token return while email verification is pending.
- Added Cognito-compatible resend and confirm operations with cooldown/idempotency, expired-state handling, and bounded admin support visibility.
- Explicitly deferred login-code/passwordless behavior until Cognito custom auth trigger support exists, with no placeholder token minting.
- Verified with focused auth lifecycle, entitlement, usage, and Ruff checks.

Known deferred items at close: full parent/admin operations visibility, production deploy/live Cognito smoke, native apps, final live Stripe/TWINT activation, and actual passwordless login-code support.

---

## v5.7 Usage Ledger And Quota Reconciliation (Completed: 2026-07-03)

**Status:** Completed local backend release gate 2026-07-03
**Started:** 2026-07-03
**Roadmap:** `.planning/milestones/v5.7-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.7-REQUIREMENTS.md`
**Audit:** `.planning/v5.7-MILESTONE-AUDIT.md`
**Phase evidence:** `.planning/milestones/v5.7-phases/`
**Goal:** Turn plan-governed usage from counter-only behavior into durable, queryable ledger events and reconcile them with quota counters.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `usage-ledger-ready`

Function purpose:

- Persist durable, privacy-safe usage ledger events for quota-governed actions.
- Reconcile ledger totals with existing daily quota counters.
- Preserve v5.6 effective entitlement and current atomic counter behavior.
- Give parents/customers and admins enough usage explanation for support without building the full v5.9 operations console.

Implementation strategy:

- Define ledger event schema and idempotency before code.
- Start with student question submissions as the first governed action.
- Keep the counter path as enforcement and add ledger/reconciliation around it.
- Expose bounded usage summaries after reconciliation behavior exists.

Completed phases:

- Phase 207: Usage Ledger Contract And Idempotency.
- Phase 208: Question Usage Ledger Recording.
- Phase 209: Quota Counter Reconciliation.
- Phase 210: Usage Visibility And Focused Tests.
- Phase 211: v5.7 Usage Ledger Release Gate.

Key accomplishments:

- Added durable, privacy-safe usage ledger rows for successful student question submissions.
- Added optional request idempotency key handling and duplicate ledger prevention.
- Kept the existing atomic daily question counter as the quota enforcement primitive.
- Added counter-versus-ledger reconciliation with read-only preview and explicit bounded counter repair.
- Added parent child usage and admin support usage/reconciliation endpoints.
- Verified with focused usage ledger, question, entitlement, and subscription operation tests plus Ruff.

Known deferred items at close: email verification and login-code policy, full parent/admin operations console, native apps, live Stripe/TWINT production activation, and ledger coverage for future quota-governed actions.

---

## v5.6 Effective Entitlements And Paid Access Enforcement (Completed: 2026-07-03)

**Status:** Completed local backend release gate 2026-07-03
**Started:** 2026-07-03
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Audit:** `.planning/v5.6-MILESTONE-AUDIT.md`
**Milestone roadmap:** `.planning/milestones/v5.6-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.6-REQUIREMENTS.md`
**Goal:** Make parent-paid or manually overridden access translate into deterministic linked-student entitlement and quota behavior.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `entitlement-ready`

Function purpose:

- Resolve effective entitlement from student profile, parent binding, parent billing, manual override, rollout controls, and billing state.
- Make student question quota use effective entitlement rather than only local student tier.
- Preserve existing billing, checkout, webhook, manual override, and daily counter behavior.
- Give parents/customers and admins enough entitlement explanation for support.

Implementation strategy:

- Start from Phase 201 current-reality audit.
- Define entitlement contract and precedence before code.
- Implement resolver service using existing single-table/repository patterns.
- Integrate resolver into question quota first.
- Keep usage ledger, verification, and full operations visibility as separate follow-up milestones.

Completed phases:

- Phase 202: Entitlement Contract And Access Policy.
- Phase 203: Entitlement Resolver Service And Parent Child Mapping.
- Phase 204: Student Paid Access Enforcement.
- Phase 205: Entitlement Visibility And Focused Tests.
- Phase 206: v5.6 Entitlement Release Gate.

Key accomplishments:

- Added an effective entitlement resolver for student, active parent binding, parent profile, provider billing, manual override, billing state, period, rollout summary, and deterministic fallback behavior.
- Made student question quota use effective entitlement limits rather than only the student's local `subscription_tier`.
- Added effective entitlement summaries to parent/customer subscription responses and admin billing responses.
- Verified with focused entitlement, question, and subscription operation tests plus Ruff.

Known deferred items at close: durable usage ledger and quota reconciliation, email verification and login-code policy, full parent/admin operations visibility, native apps, and final live Stripe/TWINT activation.

---

## v5.5 Automatic Teacher Dispatch And SLA Load Balancing (Shipped: 2026-06-15)

**Status:** Completed backend dispatch-ready release gate 2026-06-15
**Audit:** `.planning/milestones/v5.5-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v5.5-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.5-REQUIREMENTS.md`
**Phase evidence:** `.planning/milestones/v5.5-phases/`
**Goal:** Automatically route student teacher-help requests to eligible teachers/tutors, prevent double assignment, reassign timed-out work, and expose SLA/load health.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `dispatch-ready`

Function purpose:

- Reduce waiting time after a student requests human help.
- Route escalated questions to a suitable available teacher/tutor.
- Reassign timed-out dispatches and show operator SLA/load health.
- Preserve human teacher replies; this is not AI auto-answering.

Implementation strategy:

- Reuse existing request-teacher, teacher queue, takeover, reply, resolve, notification, and SLA primitives.
- Add dispatch planning, conditional claim metadata, timeout/reassignment, queue filters, and operator dashboard signals.
- Keep live calendar/payroll/native push integrations future scope.

Completed phases:

- Phase 196: Teacher Dispatch And SLA Load Balancing Contract. (complete)
- Phase 197: Dispatch Planner And Candidate Ranking. (complete)
- Phase 198: Automatic Dispatch Claim And Reassignment Worker. (complete)
- Phase 199: Teacher Queue And Operator Dispatch Visibility. (complete)
- Phase 200: v5.5 Teacher Dispatch Release Gate. (complete)

Key accomplishments:

- Defined the automatic teacher dispatch contract and state model.
- Added dispatch planner and candidate ranking from teacher/tutor profile metadata.
- Added conditional dispatch claim metadata and stale reassignment behavior.
- Updated request-teacher, teacher queue, takeover, and admin dashboard routes for dispatch state.
- Verified with focused backend tests, Ruff, and code review.

Known deferred items at close: production scheduled worker/CDK wiring, live staffing calendar integration, frontend operator dashboard implementation, native push dispatch notifications, payroll/compensation automation, and final payment/support external provider activation.

---

## v5.4 Frontend Learning Operations And Automation Dashboards (Shipped: 2026-06-15)

**Status:** Completed local frontend release gate 2026-06-15
**Audit:** `.planning/milestones/v5.4-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v5.4-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.4-REQUIREMENTS.md`
**Phase evidence:** `.planning/milestones/v5.4-phases/`
**Frontend commits:** `/Users/zhdeng/stoa-frontend` `3364a39 feat: add learning operations dashboards`; `ebeebba test: cover learning operations dashboards`
**Goal:** Make v5.2/v5.3 backend learning operations usable in frontend tutor/admin/student/parent workflows.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `frontend-ready`

Completed phases:

- Phase 191: Frontend Learning Operations And Automation Dashboard Contract.
- Phase 192: Tutor Admin Automation Review Console.
- Phase 193: Learning Operations Dashboard Integration.
- Phase 194: Student Parent Assignment Explanation UX.
- Phase 195: v5.4 Frontend Learning Operations Release Gate.

Key accomplishments:

- Defined the v5.4 frontend learning operations contract across tutor, admin, student, parent, API, state, and ownership boundaries.
- Added no-demo-fallback frontend API/types/hooks for automation preview/execute, assignment history, analytics dashboard, warehouse readiness/export, and parent progress.
- Added tutor/admin automation review console routes for preview, refusal review, approved execution, results, and assignment history.
- Added operator learning operations dashboards for sequencing coverage, assignment outcomes, quality hotspots, interventions, warehouse readiness, and export summary.
- Added student and parent assignment explanation pages without answer keys or internal ranking internals.
- Verified with frontend `npm run build`, `npm run lint`, and `npx playwright test tests/e2e/learning-operations.spec.ts`.
- Ran an Open Design finish pass against the implemented role flows. The `agent-browser` CLI was unavailable locally, so verification used Playwright e2e coverage for automation review, dashboard empty/warehouse states, and role-safe family explanations.

Known deferred items at close: production frontend deploy/live smoke, native app implementation, live warehouse/BI deployment, live notification rollout, final payment/support external activation, and automatic human teacher/tutor dispatch for student help requests.

---

## v5.3 Controlled Assignment Automation (Completed local release gate: 2026-06-15)

**Status:** Completed local release gate 2026-06-15
**Roadmap:** `.planning/milestones/v5.3-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.3-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.3-MILESTONE-AUDIT.md`
**Phase evidence:** `.planning/milestones/v5.3-phases/`
**Goal:** Convert v5.2 adaptive sequencing recommendations into controlled assignment automation with tutor/admin policy boundaries, reviewed sources, idempotent creation/delivery, and family-visible explanations.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete
**Release state:** `automation-ready`

Completed phases:

- Phase 186: Controlled Assignment Automation Contract.
- Phase 187: Automation Policy And Candidate Batch Planner.
- Phase 188: Controlled Assignment Creation And Delivery Worker.
- Phase 189: Tutor Admin Review UX Contracts And Family Visibility.
- Phase 190: v5.3 Controlled Assignment Automation Release Gate.

Key accomplishments:

- Defined autonomy levels and reviewed-source eligibility before automation expands.
- Built policy-bounded candidate batches from v5.2 recommendations, accepted AI drafts, curriculum exercises, and assignment outcomes.
- Created assignments idempotently from approved batches with current-preview binding, deterministic source IDs, conditional insert, and per-item result evidence.
- Enforced AI draft visibility before assignment materialization.
- Defined tutor/admin review controls and student/parent explanations without answer keys or internal ranking internals.

Known out of scope for this milestone: unreviewed AI-generated assignment publication, final live payment/support activation, live push/native delivery, live warehouse/BI deployment, and native app implementation.

---

## v5.2 Adaptive Sequencing And Warehouse Analytics (Shipped: 2026-06-15)

**Phases completed:** 5 phases, 5 plans, 0 tasks
**Audit:** `.planning/milestones/v5.2-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v5.2-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.2-REQUIREMENTS.md`
**Phase evidence:** `.planning/milestones/v5.2-phases/`

**Key accomplishments:**

- Defined the adaptive sequencing and warehouse analytics contract.
- Implemented multi-signal sequencing recommendations with review-gated visibility and duplicate/source suppression.
- Added assignment outcome feedback metadata, aggregate analytics signals, and parent/tutor sequencing summaries.
- Added warehouse readiness, aggregate export schemas, and operator dashboard contracts.
- Closed with rollout state `warehouse-ready` for backend/API readiness.

Known deferred items at close: live warehouse/BI deployment, scheduled export jobs, frontend operator dashboard integration, fully autonomous tutoring, automatic assignment delivery, and final payment/support provider activation.

---

## v5.1 Rich Curriculum Editor And Production Content Migration (Shipped: 2026-06-14)

**Phases completed:** 5 phases, 5 plans, 0 tasks

**Key accomplishments:**

- Defined the rich curriculum editor and migration contract across backend, frontend, content, curriculum QA, assignment, sequencing, and release ownership.
- Produced the admin/tutor rich editor UI/API handoff and UI-SPEC against existing curriculum authoring routes.
- Defined production content migration manifests, dry-run/apply validation, conflict handling, evidence, and rollback metadata.
- Defined assignment automation eligibility, duplicate prevention, sequencing signals, and role visibility while preserving review gates.
- Closed with readiness-complete rollout state; full frontend editor, production import, migration API/UI, candidate generation, and warehouse analytics remain deferred.

---

## v5.0 Native Mobile And Full Localization Governance (Shipped: 2026-06-14)

**Phases completed:** 5 phases, 5 plans, 0 tasks

**Key accomplishments:**

- Defined backend, frontend/PWA, native, localization, content, and release ownership boundaries for mobile/localization rollout.
- Produced mobile API readiness and client handoff guidance for core student, parent, tutor, admin, notification, billing, and support flows.
- Defined native notification token lifecycle, offline/read-through behavior, permission states, reconnect behavior, and deep-link routing.
- Defined localization governance, English/German catalog parity evidence, broad copy QA scope, and future-locale/RTL readiness.
- Closed v5.0 with rollout state `contract-ready`; frontend/native implementation and live activation remain deferred.

---

## v4.9 Production Notification And Native Delivery Rollout (Shipped: 2026-06-14)

**Phases completed:** 5 phases, 5 plans, 0 tasks

**Key accomplishments:**

- Defined production notification rollout ownership across backend, frontend, native, infrastructure, and providers.
- Added live WebSocket/API Gateway readiness settings, rollout modes, stale cleanup visibility, and redacted admin delivery status evidence.
- Added provider-gated email digest and push delivery with preference gating, token lifecycle records, and redacted send/refusal/failure evidence.
- Documented frontend/native notification UX, WebSocket discovery, token registration, and no-demo-fallback handoff.
- Closed with 411 backend tests passing, Ruff passing, and release state `deferred` pending external deployment/provider/frontend/native activation.

---

## Completed

### v4.6 Rich Curriculum Authoring And Analytics Foundation

**Status:** Completed local release gate 2026-06-12
**Audit:** `.planning/milestones/v4.6-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v4.6-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v4.6-REQUIREMENTS.md`
**Phases:** 4
**Plans:** 4
**Requirements:** 4/4 v4.6 requirements complete

Key accomplishments:

- Defined the curriculum authoring contract with stable public IDs, immutable version IDs, separate lifecycles, role boundaries, validation, publish manifests, rollback, archive, and audit rules.
- Added backend curriculum operations APIs for draft, review, approve/request changes, publish, rollback, archive, preview, worklist, and audit behavior.
- Added bounded curriculum analytics signals and aggregate content-quality views with public/version IDs and source segmentation.
- Preserved published-only student/parent curriculum reads and existing adaptive assignment behavior.
- Verified with 369 backend tests and full Ruff.

Known deferred items at close: rich editor UI, production content migration, warehouse BI, automatic AI publication, full adaptive sequencing, and production deployment/live smoke.

### v4.7 Payment Production Activation And Provider Automation

**Status:** Completed backend release gate 2026-06-12
**Started:** 2026-06-12
**Completed:** 2026-06-12
**Roadmap:** `.planning/milestones/v4.7-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.7-REQUIREMENTS.md`
**Phase evidence:** `.planning/phases/156-payment-production-activation-contract-and-provider-readiness/`, `.planning/phases/157-live-provider-readiness-api-checks/`, `.planning/phases/158-direct-refund-execution-and-finance-handoff/`, `.planning/phases/159-production-webhook-registration-and-rollout-controls/`, `.planning/phases/160-v4-7-payment-activation-release-gate/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Turn the v4.4 payment readiness foundation into controlled production activation automation.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete

Completed phases:

- Phase 156: Payment Production Activation Contract And Provider Readiness.
- Phase 157: Live Provider Readiness API Checks.
- Phase 158: Direct Refund Execution And Finance Handoff.
- Phase 159: Production Webhook Registration And Rollout Controls.
- Phase 160: v4.7 Payment Activation Release Gate.

Key accomplishments:

- Accepted the production payment activation contract for live credentials, price mapping, TWINT capability, webhook registration, finance acceptance, and rollout controls.
- Added admin-only live Stripe/TWINT provider readiness checks and redacted blocker states.
- Added controlled direct refund execution behind rollout controls with idempotency and finance handoff evidence.
- Added webhook readiness evidence and independent checkout/refund rollout controls.
- Closed with focused backend test/Ruff evidence and final live activation status `deferred`.

Known deferred items at close: approved live Stripe credentials, registered production webhook endpoint, TWINT production capability approval, finance acceptance, explicit rollout enablement, production notification rollout, and support provider expansion.

### v4.8 Support Provider Expansion And CRM Automation

**Status:** Completed backend release gate 2026-06-12
**Started:** 2026-06-12
**Completed:** 2026-06-12
**Roadmap:** `.planning/milestones/v4.8-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.8-REQUIREMENTS.md`
**Phase evidence:** `.planning/phases/161-support-provider-expansion-contract-and-adapter-readiness/`, `.planning/phases/162-approved-third-party-support-adapter-and-delivery-worker/`, `.planning/phases/163-retry-workers-and-two-way-ticket-synchronization/`, `.planning/phases/164-support-sla-analytics-and-controlled-crm-messaging/`, `.planning/phases/165-v4.8-support-provider-release-gate-and-operations-audit/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Expand the v4.5 internal support queue into approved provider-backed support operations and controlled CRM/customer messaging.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete

Completed phases:

- Phase 161: Support Provider Expansion Contract And Adapter Readiness.
- Phase 162: Approved Third-Party Support Adapter And Delivery Worker.
- Phase 163: Retry Workers And Two-Way Ticket Synchronization.
- Phase 164: Support SLA Analytics And Controlled CRM Messaging.
- Phase 165: v4.8 Support Provider Release Gate And Operations Audit.

Key accomplishments:

- Defined approved support provider modes, adapter readiness, payload boundaries, ticket lifecycle, retry/sync rules, SLA inputs, and controlled messaging rules.
- Added provider adapter readiness and delivery worker behavior while preserving `internal_queue` fallback.
- Added bounded retry workers and two-way provider ticket synchronization.
- Added support SLA analytics and template-gated customer/support message evidence.
- Closed with focused backend test/Ruff evidence and final provider activation state `provider-ready`.

Known deferred items at close: real external provider selection, approved production provider credentials, destination policy approval, real CRM/customer transport, and production notification/native delivery rollout.

## Recently Completed

### v5.0 Native Mobile And Full Localization Governance

**Status:** Completed local release gate 2026-06-14
**Started:** 2026-06-14
**Completed:** 2026-06-14
**Audit:** `.planning/milestones/v5.0-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v5.0-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.0-REQUIREMENTS.md`
**Phase evidence:** `.planning/milestones/v5.0-phases/171-native-mobile-and-localization-governance-contract/`, `.planning/milestones/v5.0-phases/172-mobile-app-api-readiness-and-client-handoff/`, `.planning/milestones/v5.0-phases/173-native-notification-token-and-offline-state-handoff/`, `.planning/milestones/v5.0-phases/174-localization-governance-translation-qa-and-locale-coverage/`, `.planning/milestones/v5.0-phases/175-v5-0-native-mobile-localization-release-gate-and-handoff/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Move beyond selected responsive frontend and backend locale foundations into native/mobile rollout readiness and full localization governance.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete

Completed phases:

- Phase 171: Native Mobile And Localization Governance Contract.
- Phase 172: Mobile App API Readiness And Client Handoff.
- Phase 173: Native Notification Token And Offline State Handoff.
- Phase 174: Localization Governance Translation QA And Locale Coverage.
- Phase 175: v5.0 Native Mobile Localization Release Gate And Handoff.

Key accomplishments:

- Defined backend, frontend/PWA, future native, localization, content, and release ownership boundaries.
- Produced mobile API readiness and client handoff guidance for core STOA role flows.
- Defined native notification token lifecycle, offline/read-through behavior, permission states, reconnect behavior, and deep-link routing.
- Defined localization governance, English/German catalog parity evidence, broad copy QA scope, and future-locale/RTL readiness.
- Closed with rollout state `contract-ready`; frontend/native implementation and live activation remain deferred.

Known deferred items at close: frontend demo fallback cleanup or explicit demo-only gating before `frontend-ready`; native app/APNS/FCM SDK integration, secure token storage, deep-link routing, app-store release, and native offline cache; live push/provider activation; semantic copy-owner review, hardcoded-string inventory, mobile visual text-fit QA, RTL, and future-locale activation beyond English/German.

## Recently Completed

### v5.1 Rich Curriculum Editor And Production Content Migration

**Status:** Completed readiness release gate 2026-06-14
**Started:** 2026-06-14
**Completed:** 2026-06-14
**Audit:** `.planning/milestones/v5.1-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v5.1-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.1-REQUIREMENTS.md`
**Phase evidence:** `.planning/milestones/v5.1-phases/176-rich-curriculum-editor-and-migration-contract/`, `.planning/milestones/v5.1-phases/177-admin-rich-curriculum-editor-ui-and-api-readiness/`, `.planning/milestones/v5.1-phases/178-production-content-migration-pipeline-and-validation/`, `.planning/milestones/v5.1-phases/179-assignment-automation-and-adaptive-sequencing-readiness/`, `.planning/milestones/v5.1-phases/180-v5-1-curriculum-product-release-gate-and-handoff/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Move curriculum foundations into product-ready operations with rich editor readiness, production content migration, assignment automation readiness, and adaptive sequencing readiness.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete

Completed phases:

- Phase 176: Rich Curriculum Editor And Migration Contract.
- Phase 177: Admin Rich Curriculum Editor UI And API Readiness.
- Phase 178: Production Content Migration Pipeline And Validation.
- Phase 179: Assignment Automation And Adaptive Sequencing Readiness.
- Phase 180: v5.1 Curriculum Product Release Gate And Handoff.

Feature priorities:

- Define rich editor, migration, curriculum QA, assignment, and adaptive sequencing contract.
- Prepare admin/tutor rich curriculum editor UI and API readiness.
- Define production content migration dry-run/apply/validation/rollback behavior.
- Define assignment automation and adaptive sequencing readiness.

Known deferred items at close: frontend rich curriculum editor implementation, backend rich-field payload expansion, draft update/patch, validation preview, diff and audit-read endpoints, production migration service/API/UI, source content import, candidate generation service, duplicate prevention helper, full adaptive sequencing engine, and warehouse-backed analytics.

- Close with focused curriculum product release evidence and next milestone selection.

## Earlier Completed Milestones

### v1.0 Parent Portal Real Data Integration

**Status:** Shipped 2026-06-02
**Audit:** `.planning/v1.0-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.0-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.0-REQUIREMENTS.md`
**Phases:** 5
**Plans:** 11
**Requirements:** 38/38 v1 requirements complete

Key accomplishments:

- Added normal parent portal `/parents/me/...` backend routes for child list, summary, history, latest report, and week-specific report lookups.
- Enforced parent ownership before child-specific data reads and preserved explicit legacy route compatibility.
- Aligned frontend parent services and pages to real backend route shapes without silent demo fallback.
- Added available, empty, missing, and error states across parent-critical frontend flows.
- Verified backend parent behavior with 50 tests and frontend parent flows with focused Playwright coverage.

Known deferred items at close: 4 (see `.planning/v1.0-MILESTONE-AUDIT.md` tech debt).

### v1.1 Weekly Report Automation

**Status:** Shipped 2026-06-02
**Audit:** `.planning/v1.1-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.1-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.1-REQUIREMENTS.md`
**Phases:** 8
**Plans:** 8
**Requirements:** 34/34 v1.1 requirements complete

Key accomplishments:

- Added CDK-backed scheduled weekly report Lambda infrastructure with EventBridge Scheduler, permissions, DLQ, and monitoring.
- Built weekly learning aggregation, parent-facing Bedrock report generation with deterministic fallback, and report artifact storage.
- Stored generated report metadata and full HTML/JSON artifacts before SES delivery completion.
- Added idempotent scheduled orchestration for linked parent/student report generation.
- Exposed generated, missing, pending, failed, and email-failed report states through the parent API and frontend.
- Verified backend and frontend report flows with focused pytest, ruff, Playwright, and lint coverage.

Known deferred items at close: 5 follow-up candidates (see `.planning/v1.1-MILESTONE-AUDIT.md` residual risks and follow-ups).

### v1.2 S3 Report Artifact Infrastructure

**Status:** Shipped 2026-06-04 after live AWS verification
**Milestone record:** `.planning/milestones/s3-report-artifact-infrastructure.md`
**Phase archive:** `.planning/milestones/v1.2-phases/`
**Phases:** 5
**Plans:** 5
**Requirements:** 31/31 v1.2 requirements complete

Key accomplishments:

- Verified the deployed reports bucket is private, encrypted, access-blocked, retained in CDK, and wired into both Lambda functions.
- Locked the canonical artifact key contract as `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`.
- Added helper-backed JSON/HTML artifact writes and reads with tests for content type, safe key inputs, and no S3 ACL usage.
- Preserved storage ordering so report metadata and email delivery only proceed after artifact writes succeed.
- Ran deployed Lambda private-object smoke on 2026-06-04; `stoa-weekly-report` wrote and read back a private JSON object under the canonical prefix.

Known deferred items at close: report bucket `enforce_ssl`, prefix-scoped IAM, smoke/orphan lifecycle cleanup, and report operations tooling.

### v1.3 Report Artifact Security & Operations Hardening

**Status:** Shipped 2026-06-04
**Audit:** `.planning/v1.3-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.3-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.3-REQUIREMENTS.md`
**Phases:** 4
**Plans:** 4
**Requirements:** 14/14 v1.3 requirements complete

Key accomplishments:

- Deployed HTTPS-only S3 transport enforcement on the existing reports bucket without bucket replacement.
- Scoped API and weekly report Lambda artifact S3 permissions to `weekly-reports/*`, preserving image bucket behavior.
- Added deterministic smoke cleanup and failed partial JSON artifact cleanup.
- Added admin-only report operations metadata and failed-delivery resend endpoints with persisted audit fields.
- Verified live AWS state with CDK diff/deploy, IAM checks, Lambda smoke, and S3 object absence checks.

Known deferred items at close: richer admin UI dashboard, bulk incident retry, PDF/multilanguage/billing report product expansions.

### v1.4 Report Operations Admin UI / Bulk Recovery

**Status:** Shipped 2026-06-04
**Audit:** `.planning/v1.4-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.4-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.4-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.4-phases/`
**Phases:** 5
**Plans:** 5
**Requirements:** 23/23 v1.4 requirements complete

Key accomplishments:

- Added admin report operations list/detail APIs with filters, bounded pagination, generation metadata, delivery metadata, and action eligibility.
- Added atomic single-report retry for `generation_failed` reports with retry audit fields.
- Added selected bulk resend for `email_failed` reports with per-item results and shared resend audit fields.
- Added frontend `/admin/report-operations` UI for filtering, detail inspection, single actions, selected bulk resend, and result rendering.
- Verified backend authorization/privacy, frontend e2e workflow, Lambda deployed state, API health/auth gate, and CDK diff.

Known deferred items at close: live frontend deployment of the new UI bundle, production recovery mutation smoke with an approved safe failed report target, incident-wide async recovery jobs.

### v1.5 Report Recovery Production Rollout & Live Smoke

**Status:** Shipped 2026-06-04
**Audit:** `.planning/milestones/v1.5-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.5-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.5-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.5-phases/`
**Phases:** 5
**Plans:** 5
**Requirements:** 20/20 v1.5 requirements complete

Key accomplishments:

- Verified backend and frontend release readiness, rollback entry points, deployment contract, and production evidence requirements.
- Verified production `/admin/report-operations` route and bundle markers with production API configuration and no private artifact markers.
- Fixed and verified admin report ops bounded-scan pagination, admin-auth list/detail behavior, and valid non-admin rejection.
- Ran safe non-customer generation retry, single resend, and selected bulk resend smoke with cleanup confirmation.
- Added scoped `stoa-api` SES send permission for report recovery email paths and restored current Lambda package alignment through CDK.
- Published report recovery operations runbook with observability, rollback, escalation, and known limits.

Known deferred items at close: production admin browser click-through before real support use, incident-wide async recovery jobs, immutable audit logs, support ticket integration, report editing, PDF/multilingual/billing report product expansions, and broad repo lint debt outside focused report operations files.

### v1.6 Report Recovery Operations Hardening

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v1.6-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.6-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.6-REQUIREMENTS.md`
**Goal:** Make report recovery safe for incident-wide operations by adding async bulk recovery, immutable audit evidence, production admin browser smoke, and CI/CD protection against stale Lambda package deployments.
**Phases:** 5
**Plans:** 5
**Requirements:** 28/28 complete

Key accomplishments:

- Added Lambda build manifest and CDK/CI stale-dist guard for backend Lambda package provenance.
- Added shared recovery services and application-enforced append-only audit evidence.
- Added bounded async `email_failed` resend jobs with preview, stable target snapshots, progress, per-target results, worker execution, and cooperative cancellation.
- Added admin job/audit UI on `/admin/report-operations`.
- Provisioned a long-lived production admin credential path and completed read-only production admin browser smoke with no production mutation and no private artifact marker exposure.
- Published v1.6 runbook, release gate, live verification evidence, and final milestone audit.

Known deferred items at close: incident-wide generation retry, resume failed/skipped subset, metadata-only export, support ticket integration, stronger orchestration resources if evidence requires them, compliance-grade WORM audit storage, report editing, PDF/multilingual/billing/analytics expansion, and production admin credential ownership/rotation policy.

### v1.7 Recovery Evidence Export & Admin Credential Operations

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v1.7-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.7-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.7-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.7-phases/`
**Goal:** Make production report recovery easier to operate, audit, and hand off without expanding production mutation scope.
**Phases:** 4
**Plans:** 4
**Requirements:** 7/7 complete

Key accomplishments:

- Documented long-lived production admin credential ownership, rotation, access review, emergency disable, and Cognito group verification.
- Added admin-only bounded metadata-only recovery evidence export without private artifact exposure or recovery mutation.
- Added read-only recovery evidence export controls to `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest, Lambda runtime state, CDK diff classification, API request IDs, and production browser smoke.
- Confirmed production smoke used the secret-backed admin path, exposed no private markers, and performed no production recovery mutation.

Known deferred items at close: incident-wide generation retry, failed/skipped subset resume, Step Functions/SQS or dedicated worker orchestration, WORM audit storage, support ticket/export destination integration, report editing, PDF/multilingual delivery, billing, analytics, and broader admin operations expansion.

### v1.8 Incident Generation Retry Jobs

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v1.8-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.8-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.8-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.8-phases/`
**Goal:** Admins can run bounded async `generation_failed` recovery jobs using the existing recovery job/audit platform and weekly report Lambda without expanding production mutation scope beyond approved admin actions.
**Phases:** 4
**Plans:** 4
**Requirements:** 6/6 complete

Key accomplishments:

- Defined the `retry_generation` recovery job contract and confirmed existing Lambda/DynamoDB/admin resources are sufficient.
- Added backend preview/create/execute/cancel/result/audit support for async `retry_generation` jobs.
- Routed weekly worker events through `report_recovery_retry_generation` without new infrastructure.
- Added admin report operations UI controls for resend versus generation retry job types.
- Verified backend/frontend deploys, Lambda manifest, Lambda runtime state, CDK diff classification, API request IDs, and production read-only browser smoke.
- Confirmed production smoke exposed the `Retry generation` UI, used the secret-backed admin path, exposed no private markers, and performed no production recovery mutation.

Known deferred items at close: failed/skipped subset resume, support evidence packages, Step Functions/SQS or dedicated worker orchestration if existing Lambda flow becomes insufficient, WORM audit storage, support ticket integration, report editing, PDF/multilingual delivery, billing, analytics, and broader admin operations expansion.

### v1.9 Recovery Resume And Support Evidence Packages

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v1.9-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.9-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.9-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.9-phases/`
**Goal:** Admins can resume failed/refused/not_found/skipped recovery subsets from prior jobs and generate support-safe incident evidence packages.
**Phases:** 4
**Plans:** 4
**Requirements:** 8/8 complete

Key accomplishments:

- Added backend resume preview/create support for failed/refused/not_found/skipped recovery subsets.
- Preserved source job linkage, stable target snapshots, per-target source result metadata, and append-only audit evidence.
- Added backend support evidence packages with bounded metadata-only job, target, result, and audit summaries.
- Added frontend resume and support package controls on `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest, Lambda runtime state, CDK diff classification, API request IDs, Cognito group membership, production bundle markers, and production read-only browser smoke.
- Confirmed production smoke exposed no private markers and performed no production recovery mutation.

Known deferred items at close: controlled report editing, Step Functions/SQS or dedicated worker orchestration if existing Lambda flow becomes insufficient, compliance-grade WORM audit storage, support ticket destination integration, PDF/multilingual delivery, billing, analytics, and broader admin operations expansion.

### v2.0 Controlled Report Editing MVP

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v2.0-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.0-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.0-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.0-phases/`
**Goal:** Admins can safely propose and apply bounded report content edits with append-only audit evidence and no direct S3 exposure.
**Phases:** 4
**Plans:** 4
**Requirements:** 6/6 complete

Key accomplishments:

- Defined a metadata-only report editing safety contract with no raw artifact rewrite.
- Added admin-only edit draft create/read/apply APIs for `admin_note`, `editor_summary`, and `status_note`.
- Added stale draft rejection and append-only edit audit evidence.
- Added selected-report edit draft/apply controls to `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest/runtime evidence, CDK diff classification, API request IDs, Cognito admin group membership, production bundle markers, and production read-only browser smoke.
- Confirmed production smoke exposed no private markers and performed no production edit/recovery mutation.

Known deferred items at close: raw report artifact editing/rewrite, rich preview/diff approval workflow, WORM audit storage, support ticket/export destination integrations, PDF/multilingual delivery, billing, analytics, broader admin operations expansion, and stronger recovery orchestration if existing Lambda flow becomes insufficient.

### v2.1 Report Artifact Versioning And Safe Edit Preview

**Status:** Shipped 2026-06-06
**Audit:** `.planning/milestones/v2.1-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.1-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.1-REQUIREMENTS.md`
**Goal:** Admins can preview and apply bounded report artifact edits through backend-mediated versioned artifacts, with rollback metadata, append-only audit evidence, and no frontend exposure of private S3 keys, presigned URLs, raw JSON, or unreviewed HTML.
**Phases:** 4
**Plans:** 4
**Requirements:** 7/7 complete

Key accomplishments:

- Defined the versioned artifact editing contract, rollback boundary, privacy model, and CDK readiness decision.
- Added admin-only artifact edit preview/read/apply APIs with sanitized diffs, versioned artifact writes, stale-source rejection, rollback metadata, and redacted audit evidence.
- Added selected-report artifact edit preview/apply controls to `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest/runtime evidence, CDK diff classification, API request IDs, production bundle markers, and production read-only browser smoke.
- Confirmed production smoke exposed no private markers and performed no production artifact edit mutation.

Known deferred items at close: rollback endpoint/UI, rich WYSIWYG editor, safe-fixture artifact mutation smoke, WORM audit storage, support ticket/export destination integrations, PDF/multilingual delivery, billing, analytics, broader admin operations expansion, and stronger recovery orchestration if existing Lambda flow becomes insufficient.

### v2.2 Report Artifact Rollback And Safe Fixture Verification

**Status:** Shipped 2026-06-06
**Audit:** `.planning/milestones/v2.2-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.2-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.2-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.2-phases/`
**Goal:** Admins can safely roll back report artifact versions and production verification can exercise artifact mutation only through a named non-customer safe fixture with cleanup evidence.
**Phases:** 4
**Plans:** 4
**Requirements:** 6/6 complete

Key accomplishments:

- Defined the artifact rollback contract, safe-fixture protocol, privacy model, and CDK readiness decision.
- Added admin-only artifact rollback preview/read/apply APIs with sanitized metadata, stale-source rejection, no-op rejection, and redacted audit evidence.
- Added selected-report artifact rollback preview/apply controls to `/admin/report-operations`.
- Added an explicit safe-fixture smoke harness that refuses mutation unless a fixture name and mutation mode are provided.
- Verified backend/frontend deploys, Lambda runtime state, CDK diff, production read-only API/browser smoke, and the named safe-fixture mutation/rollback/cleanup flow.
- Found and fixed a report lookup bug where artifact edit child entities could be returned from the parent GSI instead of the report summary row.

Still deferred:

- Freeform WYSIWYG report editor.
- WORM audit storage.
- Support ticket/export destination integrations.
- Step Functions/SQS or dedicated recovery orchestration.
- PDF/multilingual delivery.
- Billing, analytics, and broader admin operations expansion.

### v2.3 Release Evidence Automation And Fixture Lifecycle

**Status:** Shipped 2026-06-06
**Audit:** `.planning/milestones/v2.3-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.3-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.3-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.3-phases/`
**Goal:** Operators can produce repeatable, redacted release evidence bundles and manage the named non-customer safe fixture lifecycle without expanding production mutation scope.
**Phases:** 4
**Plans:** 4
**Requirements:** 5/5 complete

Key accomplishments:

- Defined the release evidence bundle contract, redaction model, and safe-fixture lifecycle.
- Added backend release evidence validation, fixture inventory, mutation refusal checks, CLI tooling, admin validate/status endpoints, and focused tests.
- Added read-only release evidence and safe-fixture status controls to `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest/runtime evidence, CDK diff classification, local quality gates, production API/browser smoke, and privacy denylist results.
- Confirmed safe-fixture mutation paths refuse by default and skipped optional mutation smoke without explicit mutation approval.

Known deferred items at close: compliance-grade WORM audit storage, support ticket/export integrations, richer editor/report delivery/product expansion, and dedicated orchestration if the Lambda flow becomes insufficient.

### v2.4 Support Evidence Export Destinations And Ticket Handoff

**Status:** Shipped 2026-06-07; production verification closed by v2.5
**Audit:** `.planning/milestones/v2.4-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.4-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.4-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.4-phases/`
**Goal:** Operators can turn redacted recovery, rollback, fixture, and release evidence into support-safe handoff packages for tickets or external support workflows without exposing private report artifacts or requiring unapproved third-party credentials.
**Phases:** 4
**Plans:** 4
**Requirements:** 6/6 complete locally

Key accomplishments:

- Defined the support handoff package contract, destination refusal policy, privacy model, audit metadata, and no-new-CDK-resource readiness decision.
- Added admin-only backend support handoff package generation with metadata-only recovery, release, fixture, and operator-note sections.
- Added append-only support handoff audit rows and refusal behavior for direct external writes.
- Added frontend `/admin/report-operations` support handoff controls for preview, copy, download, and refusal states.
- Verified backend and frontend quality gates, privacy denylist coverage, release evidence validation, and mutation/refusal behavior locally.

Known deferred items at close: direct support-system writes remain out of scope until an approved connector or secret-backed credential path exists.

### v2.5 Production Support Handoff Verification Closeout

**Status:** Shipped 2026-06-07
**Audit:** `.planning/milestones/v2.5-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.5-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.5-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.5-phases/`
**Goal:** Close the v2.4 production verification gap by deploying support handoff changes and recording read-only production evidence.
**Phases:** 1
**Plans:** 1
**Requirements:** 4/4 complete

Key accomplishments:

- Verified backend deploy workflow `27091480178` for commit `875a8fbe2a56c89169ba52cdf469777f72a866b7`.
- Verified frontend CI `27091612903` and deploy workflow `27091612893` for commit `9171de6109e102185dc65f41c6294f644cad72de`.
- Recorded Lambda runtime state and CDK diff classification.
- Passed production support handoff API and browser smoke with no report artifact mutation, no external support-system write, and no privacy denylist hits.

Known deferred items at close: direct support-system integrations, compliance-grade WORM audit storage, and broader report product expansion remain future work.

### v2.6 Audit Retention And Immutable Evidence Readiness

**Status:** Shipped 2026-06-07
**Audit:** `.planning/milestones/v2.6-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.6-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.6-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.6-phases/`
**Goal:** Make report operations audit evidence ready for stronger retention and future immutable storage without weakening privacy boundaries.
**Phases:** 4
**Plans:** 4
**Requirements:** 5/5 complete

Key accomplishments:

- Defined a metadata-only audit retention contract, immutability boundary, privacy model, and no-new-CDK-resource readiness decision.
- Added admin-only backend audit retention status and manifest APIs with canonical digests, privacy validation, destructive action refusal, and redacted audit metadata.
- Added frontend `/admin/report-operations` audit retention controls for status, manifest preview, copy, download, digest rendering, and refusal states.
- Verified backend/frontend deploys, Lambda runtime state, CDK diff classification, production API smoke, and production browser smoke.
- Confirmed no report artifact mutation, no audit deletion, and no external write during production smoke; only a metadata-only audit retention refusal row was written.

Known deferred items at close: compliance-grade WORM/Object Lock storage, legal hold administration, retention policy administration, and full manifest object persistence remain future scope.

### v2.7 Immutable Audit Storage And Legal Hold Foundation

**Status:** Shipped 2026-06-07
**Audit:** `.planning/milestones/v2.7-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.7-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.7-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.7-phases/`
**Goal:** Implement the foundation for CDK-managed immutable audit evidence storage and legal hold/retention policy administration for report operations audit evidence while preserving metadata-only privacy boundaries.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 5/5 complete

Key accomplishments:

- Defined immutable audit storage and legal hold contracts with CDK-managed resources as the only approved path to compliance-grade immutability.
- Added backend admin-only immutable evidence status/persist and legal hold status/apply/release metadata APIs, with immutable persistence failing closed while CDK-managed immutable storage is absent and create-only metadata object writes when configured.
- Added legal-hold compare-and-set current-state writes and consistent reads after integration audit identified the missing contract behavior.
- Added frontend `/admin/report-operations` immutable evidence and legal hold controls with separate read-only status and explicit operator-reason mutation actions.
- Verified backend/frontend deploys, Lambda runtime state, CDK diff classification, production API smoke, guarded production browser smoke, and remediation code review.
- Confirmed no report artifact mutation, no audit deletion, no immutable write, no legal-hold mutation, and no external write during production smoke.

Known deferred items at close: compliance-grade WORM/Object Lock storage, CDK-managed immutable storage resource deployment, legal/compliance retention-period review, and full immutable manifest object persistence remain future scope.

### v2.8 CDK-Managed Immutable Evidence Storage Deployment

**Status:** Shipped 2026-06-07
**Audit:** `.planning/milestones/v2.8-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.8-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.8-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.8-phases/`
**Goal:** Deploy and enable CDK-managed immutable evidence storage for report operations retention manifests, then prove full metadata-only immutable manifest object persistence in production without exposing private artifacts, deleting audit rows, or mutating customer report artifacts.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Key accomplishments:

- Defined the CDK-managed immutable evidence storage design, deploy readiness, backend configuration contract, and production verification boundary.
- Deployed a retained, versioned, Object Lock-enabled immutable evidence metadata bucket through `stoa-infra` commit `c3d0d60` and workflow run `27098074719`.
- Injected immutable storage runtime settings into `stoa-api` and verified API IAM is limited to `s3:GetObject`/`s3:PutObject` on the approved metadata prefix.
- Added backend coverage for CDK env readiness and duplicate/reference-exists refusal while preserving create-only object writer and privacy guarantees.
- Persisted one approved metadata-only immutable manifest in production and verified API, DynamoDB, S3 Object Lock headers, and browser smoke.

Known deferred items at close: formal legal/compliance approval of the 365-day GOVERNANCE retention period and operational legal-hold procedure.

### v2.9 Retention Governance And Legal Hold Operations

**Status:** Complete local-only 2026-06-07; production verification deferred
**Started:** 2026-06-07
**Audit:** `.planning/milestones/v2.9-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.9-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.9-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.9-phases/`
**Goal:** Make immutable evidence retention and legal-hold operations governable before broad compliance claims are made.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Key accomplishments:

- Defined the retention governance contract, approval packet, legal-hold runbook specification, owner model, review cadence, break-glass expectations, and privacy boundary.
- Added admin-only backend retention governance status, retention approval metadata recording, and legal-hold review metadata recording with append-only audit evidence, stale-write refusal, and privacy denylist tests.
- Added frontend `/admin/report-operations` governance controls for approval status, approval recording, legal-hold review recording, copy/download evidence payloads, and Playwright privacy coverage in `stoa-frontend` commit `b88c673`.
- Completed a local-only release gate with backend focused ruff, backend full pytest, frontend lint/build, targeted Playwright, and explicit production deploy/live smoke deferral.

Known deferred items at close: backend/frontend production deployment, production admin API smoke for governance endpoints, production browser smoke for governance controls, and formal legal/compliance approval of the exact retention period and legal-hold operating procedure. Broad compliance claims remain out of scope.

### v3.0 STOA Docs Gap Closeout And Account Intake Hardening

**Status:** Shipped 2026-06-08
**Started:** 2026-06-07
**Audit:** `.planning/milestones/v3.0-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.0-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.0-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Reconcile `stoa_docs` with the shipped backend/frontend state, close the highest-priority MVP product gaps that remain, and production-verify the v2.9 governance work before broader Phase 2 expansion.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete

Planned phases:

- Phase 87: STOA Docs Gap Audit And v3 Scope Readiness - Complete.
- Phase 88: v2.9 Governance Production Verification Closeout - Complete.
- Phase 89: Account Lifecycle And Parent Binding Gap Closeout - Complete.
- Phase 90: OCR Correction And Daily Question Quota Hardening - Complete.
- Phase 91: v3.0 Release Gate And Docs Alignment - Complete.

---
Key accomplishments:

- Produced a source-linked `stoa_docs` feature gap audit and updated it after closeout.
- Production-verified v2.9 retention governance/legal-hold operations.
- Added Cognito forgot/reset endpoints, explicit email verification metadata, formal parent-student bindings, and admin repair.
- Added edit-before-AI OCR correction, safe OCR metadata, private image-key suppression, and atomic daily question quota counters.
- Deployed backend changes, fixed API Gateway public route coverage for password reset endpoints, and passed final non-mutating production smoke.

Known deferred items at close: real email verification policy change, teacher rich text/formula polish, SLA tracking, content moderation, broad Phase 2 expansion, and unrelated `StoaNotificationStack` SES identity drift.

### v3.1 Teacher Reply Quality And SLA Operations

**Status:** Shipped 2026-06-08
**Started:** 2026-06-08
**Audit:** `.planning/milestones/v3.1-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v3.1-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v3.1-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Close the remaining teacher-takeover MVP gaps from `stoa_docs`: rich text/formula replies and response-time SLA tracking.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 92: Teacher Rich Reply And SLA Contract Readiness - Complete.
- Phase 93: Backend Rich Reply Metadata And SLA Tracking - Complete.
- Phase 94: Teacher Reply Composer And SLA Visibility UI - Complete.
- Phase 95: v3.1 Release Gate And STOA Docs Alignment - Complete.

---
Key accomplishments:

- Defined the versioned safe teacher rich reply/formula contract.
- Added backend rich reply sanitization/refusal and teacher SLA timing fields.
- Added tutor composer, formula rendering, SLA badges, and admin Teacher SLA stats.
- Completed backend/frontend deploys and production-safe smoke.

Known deferred items at close: content moderation workflow, production mutation verification for teacher rich replies with a named fixture, realtime/WebSocket teacher notifications, and broad Phase 2 expansion.

### v3.2 Content Moderation And Internal Operations

**Status:** Shipped 2026-06-08
**Started:** 2026-06-08
**Roadmap:** `.planning/milestones/v3.2-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.2-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Close the remaining MVP admin content moderation workflow from `stoa_docs`.
**Phases:** 4
**Audit:** `.planning/milestones/v3.2-MILESTONE-AUDIT.md`
**Phase archive:** `.planning/milestones/v3.2-phases/`
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 96: Content Moderation Contract And Data Model.
- Phase 97: Backend Moderation Reporting And Admin APIs.
- Phase 98: Moderation Reporting And Admin Queue UI.
- Phase 99: v3.2 Functional Release Gate And Docs Alignment.

---
Key accomplishments:

- Defined the moderation case contract, lifecycle, data model, and API/UI workflow.
- Added backend report creation and admin moderation list/detail/action APIs.
- Added student/tutor report actions and admin moderation queue/detail/actions UI.
- Completed backend/frontend deploys, production-safe smoke, and gap audit update.

Known deferred items at close: manual subscription operations, Stripe/TWINT payment-provider integration, broad multi-subject rollout, student memory/personalization, AI teacher tools, WebSocket realtime notifications, and mobile/multilingual polish.

### v3.3 Subscription Operations MVP

**Status:** Completed local release gate 2026-06-08
**Started:** 2026-06-08
**Roadmap:** `.planning/milestones/v3.3-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.3-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v3.3-phases/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Make the MVP manual subscription model usable before Stripe/TWINT integration.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 100: Subscription Operations Contract And Entitlement Model.
- Phase 101: Backend Subscription Request And Admin Tier APIs.
- Phase 102: Parent Subscription Management UI And Admin Queue.
- Phase 103: v3.3 Functional Release Gate And Billing Readiness.

---
Key accomplishments:

- Defined the subscription operations contract, request lifecycle, entitlement model, and manual billing boundary.
- Added backend parent subscription plan/request APIs and admin subscription request processing/apply APIs.
- Added parent subscription management UI and admin subscription queue/detail/actions UI.
- Completed focused local release-gate evidence and kept Stripe/TWINT as future scope.

Known deferred items at close: Stripe/TWINT payment-provider integration, broad multi-subject rollout, student memory/personalization, AI teacher tools, WebSocket realtime notifications, and mobile/multilingual polish.

### v3.4 Learning Expansion Foundation

**Status:** Complete
**Started:** 2026-06-08
**Completed:** 2026-06-08
**Phase archive:** `.planning/milestones/v3.4-phases/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Prepare Phase 2 learning expansion without jumping directly into a broad curriculum rollout.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 104: Multi-Subject Taxonomy And Prompt Contract.
- Phase 105: Backend Subject/Topic Support And Student Profile Seeds.
- Phase 106: Student And Parent Learning Profile UI.
- Phase 107: v3.4 Functional Release Gate And Expansion Audit.

Known deferred items at close: Stripe/TWINT payment-provider integration, full multi-subject curriculum content and exercises, student memory/personalization beyond profile seeds, AI teacher assistance tools, WebSocket realtime notifications, mobile responsive polish, full multilingual rollout, and support integrations.

### v3.5 Realtime And Teacher Assistance Foundation

**Status:** Complete
**Started:** 2026-06-08
**Completed:** 2026-06-08
**Audit:** `.planning/milestones/v3.5-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.5-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.5-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v3.5-phases/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Prepare realtime and teacher-assistance expansion without jumping directly into a broad WebSocket rollout or automatic exercise generation.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 108: Realtime Notification And Teacher Assistance Contract.
- Phase 109: Backend Notification Events And Teacher Summary Seeds.
- Phase 110: Tutor/Admin Notification And Summary UI.
- Phase 111: v3.5 Functional Release Gate And Expansion Audit.

Key accomplishments:

- Defined bounded notification event and teacher assistance summary seed contracts.
- Added backend notification event persistence, recipient list/read/archive APIs, admin notification listing, and teacher assistance summary seeds.
- Emitted notification events from teacher request/takeover/reply, moderation, and subscription workflows without changing their core behavior.
- Added frontend notification center, admin operational notifications, and tutor assistance seed UI.
- Completed local release-gate evidence with backend tests, focused lint, frontend lint/build, and targeted Playwright evidence.

Known deferred items at close: Stripe/TWINT payment-provider integration, production WebSocket realtime delivery, push/email notification delivery, mobile responsive polish, full multilingual rollout, and support integrations. Automatic exercise generation and richer AI teacher tools were promoted to v3.7.

### v3.6 Full WebSocket Realtime Notifications

**Status:** Completed local release gate 2026-06-09
**Started:** 2026-06-08
**Completed:** 2026-06-09
**Audit:** `.planning/milestones/v3.6-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.6-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.6-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v3.6-phases/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Turn the v3.5 in-product notification foundation into full WebSocket realtime notifications for core learning and operations workflows.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 112: Full WebSocket Transport Contract And Infra Readiness.
- Phase 113: Backend WebSocket Connection And Event Delivery.
- Phase 114: Realtime Notification Client And UX.
- Phase 115: v3.6 Functional Release Gate And Realtime Audit.

Key accomplishments:

- Defined authenticated WebSocket lifecycle, subscription, envelope, and fallback contracts.
- Added backend connection records, authorized subscription behavior, notification fanout, stale cleanup, and delivery attempt metadata.
- Added frontend WebSocket client behavior, reconnect/heartbeat/offline handling, notification cache sync, and polling fallback UX.
- Completed local backend pytest/Ruff evidence, frontend lint/build/browser fixture evidence, and documented residual production WebSocket infrastructure rollout.

Known deferred items at close: production API Gateway WebSocket/CDK route wiring, deploy/live smoke evidence, push/native notifications, email notification digests, payment provider integration, mobile polish, multilingual rollout, and support integrations. Richer AI teacher tools and automatic exercise generation were promoted to v3.7.

### v3.7 AI Teacher Tools And Exercise Generation

**Status:** Completed local release gate 2026-06-09
**Started:** 2026-06-09
**Completed:** 2026-06-09
**Audit:** `.planning/milestones/v3.7-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.7-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.7-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v3.7-phases/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Add teacher-facing automatic summaries, suggested focus, draft explanations, and bounded exercise generation with teacher/admin review.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 116: AI Teacher Tools Contract And Generation Model.
- Phase 117: Backend Teacher Summary And Exercise Draft APIs.
- Phase 118: Tutor AI Tools And Exercise Draft UI.
- Phase 119: v3.7 Functional Release Gate And AI Tools Audit.

Key accomplishments:

- Defined reviewed-draft contracts for summaries, suggested focus, draft explanations, bounded exercises, input sources, lifecycle, and no-auto-send behavior.
- Added backend AI teacher draft persistence and tutor/admin APIs for summary draft generation, exercise draft generation, list/detail, regenerate, accept, reject, and archive.
- Added tutor request detail UI for summary drafts and exercise drafts with explicit `Draft only` and `not delivered` status.
- Completed backend pytest/focused Ruff evidence, frontend lint/build/browser evidence, and updated the feature gap audit.

Known deferred items at close: automatic student assignment or delivery, long-term adaptive sequencing, production AI quality/cost monitoring, payment-provider integration, production realtime infrastructure rollout, push/native/email notifications, mobile/multilingual polish, and support integrations. Full curriculum-aligned exercise banks were promoted to v3.8.

### v3.8 Full Curriculum Rollout

**Status:** Completed local release gate 2026-06-09
**Started:** 2026-06-09
**Completed:** 2026-06-09
**Audit:** `.planning/milestones/v3.8-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.8-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.8-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v3.8-phases/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Roll out full curriculum structure and exercise bank coverage for math, physics, German, and English on top of the existing subject/topic/practice foundations.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 120: Full Curriculum Rollout Contract And Content Model.
- Phase 121: Backend Curriculum Catalog And Exercise Bank APIs.
- Phase 122: Student/Parent Curriculum UX And Tutor Signals.
- Phase 123: Functional Release Gate And Curriculum Audit.

Key accomplishments:

- Defined curriculum hierarchy, supported subjects, grade/language metadata, content lifecycle states, lesson fields, exercise fields, and backfill behavior.
- Added backend curriculum catalog, lesson detail, exercise bank, and progress APIs while preserving existing practice progress and challenge-attempt behavior.
- Added student, parent, and tutor curriculum rollout UI signals for math, physics, German, and English.
- Preserved inactive/draft/preview/archived content boundaries and answer-key authorization.
- Completed backend pytest/Ruff evidence, frontend lint/build evidence, targeted Playwright evidence, and feature gap audit closeout.

Known deferred items at close: automatic student assignment or delivery of generated exercises, long-term adaptive sequencing, rich curriculum authoring workflow, production content QA/analytics, payment-provider integration, production realtime infrastructure rollout, push/native/email notifications, mobile/multilingual polish, and support integrations.

### v3.9 Payment Provider Integration MVP

**Status:** Completed local release gate 2026-06-09
**Started:** 2026-06-09
**Completed:** 2026-06-09
**Audit:** `.planning/milestones/v3.9-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.9-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.9-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v3.9-phases/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Implement subscription checkout, provider webhook billing state, parent payment UX, and admin billing visibility for the first payment-provider integration.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 124: Payment Provider Contract And Billing Model.
- Phase 125: Backend Checkout Subscription And Webhook APIs.
- Phase 126: Parent Payment UX And Admin Billing Operations.
- Phase 127: Functional Release Gate And Billing Audit.

Key accomplishments:

- Defined the Stripe-first payment provider contract, local test-mode safety boundary, billing state model, manual override behavior, and TWINT readiness boundary.
- Added backend parent checkout session creation, parent billing status, admin billing visibility, and signed Stripe webhook lifecycle handling with idempotent event processing.
- Added provider billing status and checkout controls to the parent subscription UI while preserving the manual subscription request path.
- Added admin billing visibility for provider-managed records, lifecycle events, manual overrides, and checkout/session references.
- Completed backend pytest/Ruff evidence, frontend lint/build evidence, targeted Playwright evidence, and feature gap audit closeout.

Known deferred items at close: live production charging, real Stripe credential rollout, production TWINT validation, refunds, invoices, tax/accounting automation, dunning, provider portal handoff, and production live-payment smoke remain future rollout scope.

### v4.0 Adaptive Learning Memory And Assignment

**Status:** Completed local backend release gate 2026-06-10
**Started:** 2026-06-10
**Completed:** 2026-06-10
**Audit:** `.planning/milestones/v4.0-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v4.0-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.0-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v4.0-phases/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Add durable student memory, next-practice recommendations, reviewed assignment workflows, and parent/tutor progress signals.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 128: Adaptive Learning Memory And Assignment Contract.
- Phase 129: Backend Learning Memory And Reviewed Assignment APIs.
- Phase 130: Student/Tutor Assignment UX And Parent Progress Signals.
- Phase 131: v4.0 Functional Release Gate And Personalization Audit.

Key accomplishments:

- Defined adaptive memory fields, source inputs, assignment lifecycle, recommendation boundaries, role visibility, and stale evidence behavior.
- Added backend adaptive memory snapshot persistence and aggregation from question, feedback, practice, curriculum, and topic evidence.
- Added reviewed assignment APIs for curriculum exercises and accepted AI teacher exercise drafts.
- Added student start/complete/skip assignment lifecycle, tutor/admin assignment management, and parent progress signals.
- Completed focused Ruff/pytest evidence and adjacent learning/parent regression tests.

Known deferred items at close: production deploy/live smoke, frontend component implementation outside this backend repository, fully autonomous tutoring/assignment/sequencing, rich learning analytics dashboards, native mobile apps, production notification delivery, support integrations, rich content authoring, and deeper analytics.

### v4.1 Mobile And Multilingual Polish Foundation

**Status:** Completed local backend release gate 2026-06-11
**Started:** 2026-06-11
**Completed:** 2026-06-11
**Audit:** `.planning/milestones/v4.1-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v4.1-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.1-REQUIREMENTS.md`
**Phase evidence:** `.planning/phases/132-mobile-and-multilingual-contract-foundation/`, `.planning/phases/133-locale-preference-apis/`, `.planning/phases/134-role-route-contract-polish/`, `.planning/phases/135-release-gate-and-documentation/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Prepare STOA for mobile-friendly and multilingual product polish through backend contracts, durable locale preferences, language-safe response metadata, and release evidence before broader UI rollout.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 132: Mobile And Multilingual Contract Foundation.
- Phase 133: Locale Preference APIs.
- Phase 134: Role Route Contract Polish.
- Phase 135: Release Gate And Documentation.

Key accomplishments:

- Defined the backend/client mobile and multilingual contract, including `en`/`de` support, fallback behavior, no backend device sniffing, and deferred frontend/native ownership.
- Added shared locale normalization/fallback and durable profile locale update support.
- Extended `/auth/me` with `preferredLocale` and `effectiveLocale` while preserving `preferredLanguage`.
- Added `PATCH /auth/me/preferences/locale` for authenticated locale preference updates.
- Added additive locale metadata to adaptive student, parent, tutor, and admin route responses with tests proving canonical values remain stable across `de` and `en`.
- Completed full backend pytest evidence with 325 passing tests.

Known deferred items at close: production deploy/live smoke, full responsive frontend/native implementation, visual localization and translated UI copy, RTL verification, machine translation or translation management, production notification delivery, live payment-provider rollout, support integrations, rich content authoring, and deeper analytics/compliance operations.

### v4.2 Production Notification Delivery Readiness

**Status:** Completed local backend release gate 2026-06-11
**Started:** 2026-06-11
**Completed:** 2026-06-11
**Audit:** `.planning/milestones/v4.2-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v4.2-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.2-REQUIREMENTS.md`
**Phase evidence:** `.planning/phases/136-production-notification-infrastructure-contract/`, `.planning/phases/137-websocket-delivery-operations-and-preference-apis/`, `.planning/phases/138-email-digest-and-push-preference-readiness/`, `.planning/phases/139-v4.2-functional-release-gate-and-notification-delivery-audit/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Promote STOA's local realtime notification foundation into production-deliverable notification capability through production WebSocket delivery contracts, delivery operations, durable preferences, email digest readiness, and focused release evidence.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 136: Production Notification Infrastructure Contract.
- Phase 137: WebSocket Delivery Operations And Preference APIs.
- Phase 138: Email Digest And Push Preference Readiness.
- Phase 139: v4.2 Functional Release Gate And Notification Delivery Audit.

Key accomplishments:

- Defined production WebSocket endpoint, API Gateway route/integration expectations, fallback behavior, delivery state fields, and ownership boundaries.
- Added durable user notification preferences for in-app, realtime, email digest, and push-ready channels.
- Added preference-aware delivery decision metadata and realtime fanout gating while preserving in-product notification defaults.
- Added bounded admin/operator delivery status aggregates.
- Added digest preview selection with category/window filtering, metadata-safe payloads, preview-only behavior, and explicit no-provider email/push fallback metadata.
- Completed full backend pytest and full ruff release-gate evidence.

Known deferred items at close: CDK/API Gateway WebSocket production route wiring, live production notification smoke, frontend/native notification surfaces, native push provider rollout, production email digest templates/scheduling, and broader notification analytics remain future rollout scope.

### v4.3 Frontend Mobile And Visual Localization Rollout

**Status:** Completed local frontend release gate 2026-06-11
**Started:** 2026-06-11
**Completed:** 2026-06-11
**Audit:** `.planning/milestones/v4.3-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v4.3-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.3-REQUIREMENTS.md`
**Phase evidence:** `.planning/phases/140-frontend-workspace-contract-and-mobile-uat-plan/`, `.planning/phases/141-responsive-student-parent-tutor-core-flow-polish/`, `.planning/phases/142-visual-localization-and-language-preference-ui/`, `.planning/phases/143-v4.3-browser-release-gate-and-localization-audit/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Use `/Users/zhdeng/stoa-frontend` to implement responsive mobile UX and visible English/German localization for selected core STOA workflows.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 140: Frontend Workspace Contract And Mobile UAT Plan.
- Phase 141: Responsive Student Parent Tutor Core Flow Polish.
- Phase 142: Visual Localization And Language Preference UI.
- Phase 143: v4.3 Browser Release Gate And Localization Audit.

Key accomplishments:

- Confirmed `/Users/zhdeng/stoa-frontend` framework, route, API client, i18n, and verification contracts before frontend implementation.
- Improved shared mobile buttons, page actions, app shell navigation, and tutor AI teacher tool layouts for selected core flows.
- Added targeted Playwright mobile viewport coverage for student, parent, tutor, and admin flows.
- Wired authenticated English/German language preference changes to the backend locale preference API.
- Applied `/auth/me` locale state on refresh and verified German UI persistence through browser reload.
- Completed frontend lint, production build, and targeted browser release-gate evidence.

Known deferred items at close: native mobile apps, full translation management and broad copy QA, RTL support, production frontend deploy/live smoke, full production notification rollout, live payment-provider rollout, support integrations, rich curriculum authoring, analytics, and deeper compliance operations.

### v4.4 Live Payment Provider Rollout

**Status:** Completed local release gate 2026-06-11
**Started:** 2026-06-11
**Completed:** 2026-06-11
**Roadmap:** `.planning/milestones/v4.4-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.4-REQUIREMENTS.md`
**Phase evidence:** `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/`, `.planning/phases/145-production-checkout-webhook-and-twint-capable-stripe-gating/`, `.planning/phases/146-billing-operations-invoices-refunds-dunning-and-swiss-handoff/`, `.planning/phases/147-v4-4-payment-release-gate-rollout-controls-and-support-audit/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Move STOA's local Stripe-first payment provider MVP toward controlled live rollout and operator-ready billing operations.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 144: Live Payment Rollout Contract And Credential Readiness.
- Phase 145: Production Checkout And Webhook Verification.
- Phase 146: Refunds Invoices Tax And Dunning Readiness.
- Phase 147: v4.4 Payment Release Gate And Support Audit.

Key accomplishments:

- Defined the live Stripe rollout contract, credential path, product/price mapping, TWINT inclusion, safe smoke modes, and rollback switches.
- Added fail-closed live readiness states, Stripe SDK wiring, TWINT-capable Checkout configuration, and signed webhook verification defaults.
- Tightened entitlement behavior around authoritative invoice/subscription events and preserved active subscriptions when replacement checkouts expire.
- Added provider lookup rows and parent/admin billing readiness surfaces.
- Added invoice/receipt metadata, non-mutating refund handoff, dunning/recovery projections, Swiss accounting export metadata, and TWINT lifecycle propagation.
- Completed focused backend payment tests, static checks, rollback controls audit, release evidence, and remaining payment work audit.

Known deferred items at close: approved Stripe live credentials, production webhook endpoint registration, TWINT account capability confirmation, explicit live-charge approval, direct refund execution, broader accounting/support destination integration, provider-readiness API checks, expanded dunning automation, and multi-provider billing automation.

### v4.5 Support Evidence Integrations And Operations Handoff

**Status:** Completed local backend release gate 2026-06-12
**Started:** 2026-06-12
**Completed:** 2026-06-12
**Audit:** `.planning/milestones/v4.5-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v4.5-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.5-REQUIREMENTS.md`
**Phase evidence:** `.planning/phases/148-support-destination-contract-and-credential-readiness/`, `.planning/phases/149-support-evidence-export-destination-integration/`, `.planning/phases/150-operator-queue-and-handoff-status-visibility/`, `.planning/phases/151-v4-5-support-integration-release-gate/`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Connect support-safe evidence packages to approved operational destinations and expose operator-visible handoff status while preserving metadata-only privacy and fail-closed external writes.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 148: Support Destination Contract And Credential Readiness.
- Phase 149: Support Evidence Export Destination Integration.
- Phase 150: Operator Queue And Handoff Status Visibility.
- Phase 151: v4.5 Support Integration Release Gate.

Key accomplishments:

- Defined support destination modes, credential/readiness states, payload boundaries, attachment policy, lifecycle vocabulary, and refusal behavior before enabling any support-system write.
- Selected `internal_queue` as the first approved path with `none_required` credentials and `SUPPORT_INTERNAL_QUEUE_APPROVED=true` as the rollout approval gate.
- Added fail-closed admin-only support handoff delivery that preserves manual preview/copy/download fallback and refuses contract-defined third-party destinations.
- Added operator-visible delivery queue/detail endpoints with lifecycle state, bounded audit visibility, metadata-only response shaping, and read-only retry eligibility.
- Added provider-failure lifecycle coverage and release-gate evidence with imported Phase 68/69/70 frontend support handoff evidence.
- Completed focused support handoff tests, full admin report ops tests, Ruff, phase verification, and milestone integration audit.

Known deferred items at close: third-party support provider credentials/adapters, retry mutation workers, single stitched create-delivery to queue/detail integration test with real repository helpers, two-way ticket synchronization, support SLA analytics, and broader CRM/customer messaging automation.

---
*Last updated: 2026-06-14 after selecting v5.1 rich curriculum editor and production content migration*
