# Requirements: v5.20 Native Build Distribution And Device QA

**Milestone:** v5.20
**Status:** Active
**Created:** 2026-07-06
**Prior milestone:** v5.19 Native Mobile Push And Offline Client Implementation

## Purpose

Make native mobile real on devices, not only in source code. v5.20 should produce internal build artifacts, device QA evidence, push/deep-link smoke, crash/performance telemetry boundaries, and a store-readiness checklist without claiming public launch.

## Requirements

### MOBILEBUILD-01 Native Build And Credential Readiness

Acceptance criteria:

- App identifiers, bundle IDs, package names, EAS project state, signing credentials, notification credentials, and release channels are documented.
- Missing or unapproved credentials close as blocked with exact owner/action, not as silent skips.
- Environment profiles separate local, staging, production read-only, and approved safe-fixture behavior.
- No production customer mutation is required for internal device smoke.

### MOBILEBUILD-02 Internal Build Distribution Pipeline

Acceptance criteria:

- Internal iOS and Android build commands/profiles are documented and repeatable.
- Build artifacts include version, commit SHA, profile, API environment, created timestamp, and distribution audience.
- Release channel and rollback instructions are documented.
- Build output never embeds secrets, private S3 keys, Cognito token material, or provider payloads in evidence.

### MOBILEBUILD-03 Device QA Matrix And Mobile Smoke

Acceptance criteria:

- Device QA covers at least one iOS phone and one Android phone, or records exact blocker if hardware/accounts are unavailable.
- Smoke covers sign-in/session restore, student dashboard/practice, parent child summary/report, push permission/token registration, notification deep link, offline read-through, and sign-out cleanup.
- Redacted screenshots or logs prove support-safe state without private learning content, provider payloads, or secrets.
- Known device-specific issues are classified as blocking, non-blocking, or deferred with owner and next action.

### MOBILEBUILD-04 Mobile Crash Performance And Release Telemetry

Acceptance criteria:

- Mobile release health exposes low-cardinality build, version, route, account-state, push-state, and offline-state signals.
- Crash/performance telemetry avoids raw content, tokens, provider payloads, private IDs, and high-cardinality free text.
- Operator summary distinguishes product regression, provider blocker, stale/offline state, user-denied notification permission, and credential/config blocker.
- Runbook defines triage, suppression, rollback, and escalation behavior.

### VERIFY-54 Native Distribution Release Gate

Acceptance criteria:

- Build, device QA, telemetry, push/deep-link, offline, and release-channel evidence is recorded.
- Store-readiness checklist covers account ownership, privacy declarations, notification use, screenshots, review notes, rollback, and rollout approval.
- Roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.
- Remaining native credential, app-store, production rollout, and device-coverage blockers are explicit.

## Out of Scope

- Public App Store or Play Store launch without explicit release approval.
- Native in-app purchases or app-store commerce.
- Broad beta-program operations beyond internal distribution.
- Full offline mutation.
- New product features unrelated to proving native build/device readiness.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILEBUILD-01 | Phase 272 | Planned |
| MOBILEBUILD-02 | Phase 273 | Planned |
| MOBILEBUILD-03 | Phase 274 | Planned |
| MOBILEBUILD-04 | Phase 275 | Planned |
| VERIFY-54 | Phase 276 | Planned |
