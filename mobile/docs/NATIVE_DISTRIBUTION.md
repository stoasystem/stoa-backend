# STOA Mobile v5.20 Native Distribution Evidence

**Milestone:** v5.20 Native Build Distribution And Device QA
**Release state:** `native-distribution-ready-local-contracts`

## Scope

v5.20 adds native build distribution and device QA contracts on top of the v5.19 source-ready mobile client. It does not claim that EAS builds, physical-device smoke, or app-store launch succeeded in this local workspace.

## Credential Readiness

- Expo project ID: blocked until real EAS project state is provided.
- Apple Developer account/signing/APNs: blocked until team, bundle ID, certificates/profiles, and APNs capability are confirmed.
- Google Play/Android signing/FCM: blocked until package ownership, upload key policy, internal track, and FCM credentials are confirmed.
- Production rollout approval: blocked until cohort, mutation policy, support staffing, rollback, and monitoring are approved.

## Build Distribution

Internal build commands are defined in `mobile/src/release/buildDistribution.ts`:

- `eas build --platform all --profile development`
- `eas build --platform all --profile preview`

Build artifact evidence must include build ID, commit SHA, profile, platform, API environment, creation timestamp, distribution audience, and release channel. Evidence must not include secrets, token material, provider payloads, private object keys, or Cognito material.

## Device QA

Required minimum device matrix:

- one supported iOS phone
- one supported Android phone

Local state: blocked until physical devices and signing/build evidence are available.

Smoke coverage:

- sign-in/session restore
- student dashboard and practice
- parent child summary/report
- push token registration and notification deep link
- offline read-through stale state
- sign-out cleanup

## Telemetry Boundary

Mobile release health is low-cardinality only: build profile, app version, route group, account state, push state, offline state, and blocker category. Raw prompts, answers, transcripts, tokens, secrets, provider payloads, billing payloads, private IDs, private object keys, and free text are forbidden.

## Store Readiness

Store launch remains out of scope. Store readiness requires account ownership, privacy declarations, screenshots/review notes, support staffing, rollout approval, monitoring, rollback, and explicit go/no-go decision.
