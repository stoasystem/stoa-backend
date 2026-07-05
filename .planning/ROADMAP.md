# Roadmap: v5.20 Native Build Distribution And Device QA

**Status:** Active
**Created:** 2026-07-06
**Prior milestone:** v5.19 Native Mobile Push And Offline Client Implementation

## Goal

Turn the v5.19 native mobile implementation into internal device-ready releases with build distribution, native credential evidence, physical-device QA, push/deep-link smoke, crash/performance telemetry, and app-store readiness artifacts.

## Why This Follows v5.19

v5.19 proved that the mobile client can consume real STOA backend contracts. v5.20 should then prove that the client can actually run as a distributed native build on devices, receive native notifications, survive session/offline edge cases, and be prepared for controlled store submission when release approval exists.

## Product Purpose

- Internal testers can install and use STOA on real iOS and Android devices.
- Product and support can verify mobile auth, student/parent journeys, push, deep links, and offline stale-state behavior outside the simulator.
- Release owners can see exactly which native credentials, store assets, privacy declarations, and rollout controls are ready or blocked.

## Implementation Strategy

- Add EAS/internal-distribution configuration only after native app routes and environment contracts are stable.
- Keep production rollout gated; internal builds may hit staging or approved production read-only/safe-fixture paths only.
- Run a small device QA matrix across iOS and Android before adding broader store work.
- Wire low-cardinality crash/performance/mobile release signals into existing observability contracts instead of creating a parallel analytics model.
- Close with build IDs, device QA evidence, push/deep-link evidence, store-readiness checklist, and explicit remaining blockers.

## Phases

- [ ] **Phase 272: Native Build And Credential Readiness Audit** - Map current mobile implementation, native credentials, build profiles, app identifiers, and environment prerequisites.
- [ ] **Phase 273: Internal Build Distribution Pipeline** - Configure EAS/build profiles, signed internal builds, release channels, versioning, and artifact evidence.
- [ ] **Phase 274: Device QA Matrix And Mobile Smoke** - Run physical-device auth, parent/student, push, deep-link, offline, and localization smoke with redacted evidence.
- [ ] **Phase 275: Mobile Crash Performance And Release Telemetry** - Add mobile crash/performance/status telemetry boundaries and operator-visible release-health summaries.
- [ ] **Phase 276: v5.20 Native Distribution Release Gate** - Close with device evidence, store-readiness checklist, rollout blockers, and next milestone decision.

## Phase Details

### Phase 272: Native Build And Credential Readiness Audit

**Goal**: Map current mobile implementation, native credentials, build profiles, app identifiers, and environment prerequisites.
**Requirements**: MOBILEBUILD-01
**Success Criteria**:

1. App identifiers, bundle IDs, package names, EAS project state, signing credentials, notification credentials, and release channels are documented.
2. Missing or unapproved credentials close as blocked with exact owner/action, not as silent skips.
3. Environment profiles separate local, staging, production read-only, and approved safe-fixture behavior.
4. No production customer mutation is required for internal device smoke.

### Phase 273: Internal Build Distribution Pipeline

**Goal**: Configure EAS/build profiles, signed internal builds, release channels, versioning, and artifact evidence.
**Requirements**: MOBILEBUILD-02
**Success Criteria**:

1. Internal iOS and Android build commands/profiles are documented and repeatable.
2. Build artifacts include version, commit SHA, profile, API environment, created timestamp, and distribution audience.
3. Release channel and rollback instructions are documented.
4. Build output never embeds secrets, private S3 keys, Cognito token material, or provider payloads in evidence.

### Phase 274: Device QA Matrix And Mobile Smoke

**Goal**: Run physical-device auth, parent/student, push, deep-link, offline, and localization smoke with redacted evidence.
**Requirements**: MOBILEBUILD-03
**Success Criteria**:

1. Device QA covers at least one iOS phone and one Android phone, or records exact blocker if hardware/accounts are unavailable.
2. Smoke covers sign-in/session restore, student dashboard/practice, parent child summary/report, push permission/token registration, notification deep link, offline read-through, and sign-out cleanup.
3. Redacted screenshots or logs prove support-safe state without private learning content, provider payloads, or secrets.
4. Known device-specific issues are classified as blocking, non-blocking, or deferred with owner and next action.

### Phase 275: Mobile Crash Performance And Release Telemetry

**Goal**: Add mobile crash/performance/status telemetry boundaries and operator-visible release-health summaries.
**Requirements**: MOBILEBUILD-04
**Success Criteria**:

1. Mobile release health exposes low-cardinality build, version, route, account-state, push-state, and offline-state signals.
2. Crash/performance telemetry avoids raw content, tokens, provider payloads, private IDs, and high-cardinality free text.
3. Operator summary distinguishes product regression, provider blocker, stale/offline state, user-denied notification permission, and credential/config blocker.
4. Runbook defines triage, suppression, rollback, and escalation behavior.

### Phase 276: v5.20 Native Distribution Release Gate

**Goal**: Close with device evidence, store-readiness checklist, rollout blockers, and next milestone decision.
**Requirements**: VERIFY-54
**Success Criteria**:

1. Build, device QA, telemetry, push/deep-link, offline, and release-channel evidence is recorded.
2. Store-readiness checklist covers account ownership, privacy declarations, notification use, screenshots, review notes, rollback, and rollout approval.
3. Roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.
4. Remaining native credential, app-store, production rollout, and device-coverage blockers are explicit.

## Future Milestone Directions

- **v5.21 AI Teaching Quality Cost And Safety Operations**: after mobile distribution exists, make AI teaching behavior measurable, controllable, and support-visible across web and mobile clients.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILEBUILD-01 | Phase 272 | Planned |
| MOBILEBUILD-02 | Phase 273 | Planned |
| MOBILEBUILD-03 | Phase 274 | Planned |
| MOBILEBUILD-04 | Phase 275 | Planned |
| VERIFY-54 | Phase 276 | Planned |
