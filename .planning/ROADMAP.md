# Roadmap: v5.25 Pilot Activation Blocker Burn-Down And Safe Start Decision

**Status:** Complete
**Created:** 2026-07-07
**Prior milestone:** v5.24 Limited Production Pilot And Launch Readiness

## Goal

Turn v5.24's conditional limited-pilot recommendation into an executable safe-start decision by clearing, explicitly disabling, or routing every real-user activation blocker before any pilot cohort is enabled.

## Why This Follows v5.24

v5.24 produced the pilot scope, launch controls, metrics, and go/no-go contract, but it also left hard activation blockers: payment, notifications, support CRM, BI/APM, mobile store/TestFlight, production restore, and live tabletop readiness. The next milestone must burn those down before claiming pilot execution.

## Product Purpose

- Protect the first real pilot from half-enabled providers and unclear operational ownership.
- Make every blocker visible as cleared, explicitly disabled for pilot scope, or launch-blocking.
- Prepare a pilot start package that operators can actually run.

## Implementation Strategy

- Start from the v5.24 blocker list and current provider/readiness APIs.
- Prefer approved live activation where credentials and owners exist.
- If a dependency is not required for the pilot, explicitly disable it in the pilot scope and document user/support impact.
- Run pilot dry-run accounts and launch-room rehearsal before enabling real users.
- Close with a safe-start decision: start pilot, hold, or harden further.

## Phases

- [x] **Phase 297: Pilot Activation Blocker Reality Audit** - Re-check payment, notification, support CRM, BI/APM, mobile release, restore, tabletop, staffing, and data readiness against current code/config. (completed 2026-07-07)
- [x] **Phase 298: Provider Activation Or Explicit Disablement** - Clear or explicitly disable required provider dependencies for the limited pilot scope. (completed 2026-07-07)
- [x] **Phase 299: Pilot Environment Cohort And Account Dry Run** - Validate pilot accounts, cohort setup, entitlement, onboarding, mobile install, support path, and rollback communication with fixtures. (completed 2026-07-07)
- [x] **Phase 300: Launch Room Rehearsal And Safe Start Package** - Rehearse launch-room monitoring, incident escalation, rollback, support staffing, and daily pilot reporting. (completed 2026-07-07)
- [x] **Phase 301: Pilot Safe Start Gate** - Produce start/hold/harden decision evidence and update next milestone scope. (completed 2026-07-07)

## Phase Details

### Phase 297: Pilot Activation Blocker Reality Audit

Goal: Re-check payment, notification, support CRM, BI/APM, mobile release, restore, tabletop, staffing, and data readiness against current code/config.

Completion evidence:

- `production_pilot_service.activation_blocker_reality_audit`

### Phase 298: Provider Activation Or Explicit Disablement

Goal: Clear or explicitly disable required provider dependencies for the limited pilot scope.

Completion evidence:

- `production_pilot_service.provider_activation_or_disablement`

### Phase 299: Pilot Environment Cohort And Account Dry Run

Goal: Validate pilot accounts, cohort setup, entitlement, onboarding, mobile install, support path, and rollback communication with fixtures.

Completion evidence:

- `production_pilot_service.pilot_environment_cohort_dry_run`

### Phase 300: Launch Room Rehearsal And Safe Start Package

Goal: Rehearse launch-room monitoring, incident escalation, rollback, support staffing, and daily pilot reporting.

Completion evidence:

- `production_pilot_service.launch_room_rehearsal_safe_start_package`

### Phase 301: Pilot Safe Start Gate

Goal: Produce start/hold/harden decision evidence and update next milestone scope.

Completion evidence:

- `production_pilot_service.pilot_safe_start_gate`

## Future Milestone Directions

- **v5.26 Limited Pilot Execution And Outcome Evidence**: run the approved pilot cohort, operate daily monitoring/support, collect evidence, and decide whether to continue, pause, roll back, or remediate.
- **v5.27 Pilot Remediation And Product Fit Hardening**: fix the highest-impact pilot issues across account activation, mobile, AI, curriculum, support, and reliability.
- **v5.28 Controlled Expansion Revenue And Operations Scale**: expand to a larger controlled cohort with revenue, staffing, mobile, support, and operational scale controls.
- **v5.29 Public Launch Readiness Growth And Self-Serve Onboarding**: prepare self-serve onboarding, growth loops, pricing/package readiness, and public launch go/no-go.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PILOTSTART-01 | Phase 297 | Complete |
| PILOTSTART-02 | Phase 298 | Complete |
| PILOTSTART-03 | Phase 299 | Complete |
| PILOTSTART-04 | Phase 300 | Complete |
| VERIFY-59 | Phase 301 | Complete |
