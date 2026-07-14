# STOA Mobile v5.19 Release Evidence

**Date:** 2026-07-06
**Milestone:** v5.19 Native Mobile Push And Offline Client Implementation
**Release state:** `native-mobile-source-ready-local`

## Implemented Source Evidence

- Expo SDK 57 TypeScript mobile workspace under `mobile/`.
- App shell and Expo Router route boundaries for auth, student, parent, notifications, and blocked account states.
- Mobile environment contract for API, Cognito, Expo project ID, release channel, and no-demo-fallback mode.
- Amplify/Cognito auth/session wrappers for sign-in, registration, email verification, resend-code, session restore, token access, and sign-out.
- Metadata-only SecureStore policy; no raw token persistence.
- Authenticated API client wrapper.
- Support-safe account-state mapper.
- Student adapters for profile, dashboard summary, practice/curriculum, questions, teacher help, history, and notifications.
- Parent adapters for children, subscription, billing, account operations, child summary/history/report/usage/learning profile, and notifications.
- Expo push permission/token contract plus backend push-token registration/revocation adapter.
- Notification read/archive adapter and authenticated deep-link validation.
- Read-through cache policy, SQLite helper, sensitive-cache category guard, and online-only mutation guard.
- English/Chinese mobile copy fixtures for core journey labels.

## Verification

Focused local checks:

```bash
pytest tests/mobile
```

Expected local result:

- 26 passed
- 1 existing pytest config warning for `asyncio_mode` under the local Python 3.11 pytest environment

## Not Claimed In v5.19

- Mobile dependencies were declared but not installed in this workspace during v5.19.
- Expo native build was not run.
- EAS internal build was not run.
- Physical-device iOS/Android QA was not run.
- Live push delivery smoke was not run.
- Public App Store or Play Store launch was not attempted.

## Blockers And Prerequisites

| Area | State | Required Before Claiming Live Readiness |
|------|-------|------------------------------------------|
| Dependency install | Blocked in v5.19 scope | Run package install in `mobile/` and commit lockfile once package manager is selected. |
| Expo/EAS project | Blocked | Provide real Expo project ID and EAS project configuration. |
| Android push | Blocked | Configure FCM credentials for production push. |
| iOS push | Blocked | Configure Apple Developer account and APNs credentials. |
| Device QA | Blocked | Run iOS and Android physical-device matrix. |
| Store launch | Out of scope | Complete store assets, privacy labels, review requirements, support staffing, rollout/rollback plan, and release approval. |

## No-Demo-Fallback Evidence

- `mobile/src/config/mobileConfig.ts` defaults `EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK` to enabled.
- Authenticated adapters use backend endpoint paths; no fixture user IDs or demo responses are embedded.
- Release evidence does not include raw prompts, answers, teaching transcripts, report artifacts, provider payloads, billing payloads, Cognito token material, secrets, or private object keys.

## Next Milestone

v5.20 should focus on native build distribution and device QA: dependency installation, lockfile, EAS credentials, internal builds, physical-device push/deep-link smoke, crash/performance telemetry, and store-readiness evidence.
