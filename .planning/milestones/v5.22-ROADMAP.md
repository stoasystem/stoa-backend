# Roadmap: v5.22 Support CRM Customer Messaging And Lifecycle Automation

**Status:** Completed
**Created:** 2026-07-06
**Prior milestone:** v5.21 AI Teaching Quality Cost And Safety Operations

## Goal

Make support handoff, CRM/customer messaging, parent onboarding, lifecycle nudges, account-status messaging, and support-visible customer operations usable end to end without exposing private learning content or relying on manual operator stitching.

## Why This Follows v5.21

Support provider adapters, support-safe handoff packages, CRM messaging gates, notification foundations, account operations, billing evidence, and AI/teacher state already exist in pieces. v5.22 connects them into usable customer lifecycle operations after AI quality/safety signals are clear enough to include in support and parent communication.

## Product Purpose

- Parents receive timely, relevant onboarding, billing, verification, usage, progress, and support-status messages.
- Operators can see support lifecycle and CRM message state without reading raw student work or provider payloads.
- Customer messaging becomes governed product infrastructure, not ad hoc manual outreach.

## Implementation Strategy

- Audit current support handoff, CRM messaging, notification preference, account operations, billing, AI, and parent progress state before adding workflows.
- Use approved templates, preference gates, opt-out handling, and support-safe summaries.
- Prefer lifecycle state machines and idempotent message jobs over one-off sends.
- Keep external provider writes gated by credentials and destination approval.
- Close with journey evidence for onboarding, blocked verification, payment lifecycle, support incident, and learning-progress nudges.

## Phases

- [x] **Phase 282: Customer Lifecycle Reality Audit And Message Taxonomy** - Map lifecycle events, templates, preferences, provider gates, and missing customer-message evidence. (completed 2026-07-06)
- [x] **Phase 283: Lifecycle Messaging Orchestrator** - Add idempotent lifecycle jobs for onboarding, verification, billing, quota, progress, support, and re-engagement states. (completed 2026-07-06)
- [x] **Phase 284: Parent And Admin Messaging Surfaces** - Add visible parent/admin support-safe message history, status, retry, opt-out, and explanation surfaces. (completed 2026-07-06)
- [x] **Phase 285: Support CRM Provider Activation Smoke** - Verify approved-provider ticket/message flows, refusal states, retry/sync behavior, and provider blockers. (completed 2026-07-06)
- [x] **Phase 286: v5.22 Customer Lifecycle Release Gate** - Close with journey evidence, template evidence, provider-state evidence, and next milestone decision. (completed 2026-07-06)

## Phase Details

### Phase 282: Customer Lifecycle Reality Audit And Message Taxonomy

Goal: Map lifecycle events, templates, preferences, provider gates, and missing customer-message evidence.

Deliverables:

- Customer lifecycle taxonomy covering onboarding, verification, billing, quota, subscription, support, progress, and re-engagement events.
- Support-safe payload field contract and privacy denylist.
- Provider/template/destination gating policy.

Completion evidence:

- `customer_lifecycle_service.message_taxonomy`
- `tests/test_customer_lifecycle.py`

### Phase 283: Lifecycle Messaging Orchestrator

Goal: Add idempotent lifecycle jobs for onboarding, verification, billing, quota, progress, support, and re-engagement states.

Deliverables:

- Deterministic idempotency keys.
- Preference, opt-out, quiet-hour, provider, template, destination, and stale-state gates.
- Retry/backoff and duplicate suppression contracts.

Completion evidence:

- `customer_lifecycle_service.plan_lifecycle_message`
- `customer_lifecycle_service.plan_lifecycle_journey`

### Phase 284: Parent And Admin Messaging Surfaces

Goal: Add visible parent/admin support-safe message history, status, retry, opt-out, and explanation surfaces.

Deliverables:

- Parent-facing message history projection.
- Admin/operator message lifecycle projection.
- Support-safe provider state and retry metadata.

Completion evidence:

- `customer_lifecycle_service.parent_message_history`
- `customer_lifecycle_service.admin_message_history`

### Phase 285: Support CRM Provider Activation Smoke

Goal: Verify approved-provider ticket/message flows, refusal states, retry/sync behavior, and provider blockers.

Deliverables:

- Safe fixture provider activation smoke.
- Refusal states for missing approval, credential, template, destination, opt-out, and provider failure.
- Metadata-only provider evidence.

Completion evidence:

- `customer_lifecycle_service.provider_activation_smoke`

### Phase 286: v5.22 Customer Lifecycle Release Gate

Goal: Close with journey evidence, template evidence, provider-state evidence, and next milestone decision.

Deliverables:

- Release gate evidence for journey coverage, template inventory, provider blockers, disable controls, and privacy.
- Milestone audit and completed snapshots.

Completion evidence:

- `customer_lifecycle_service.release_gate_evidence`
- `.planning/milestones/v5.22-MILESTONE-AUDIT.md`

## Future Milestone Directions

- **v5.23 Enterprise Stability Compliance And Disaster Recovery Hardening**: after customer operations are connected, harden operational resilience, incident response, restore, access, and rollback.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| LIFECYCLE-01 | Phase 282 | Complete |
| LIFECYCLE-02 | Phase 283 | Complete |
| LIFECYCLE-03 | Phase 284 | Complete |
| LIFECYCLE-04 | Phase 285 | Complete |
| VERIFY-56 | Phase 286 | Complete |
