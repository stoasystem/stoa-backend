# v5.19 Research: Architecture

## Recommended Client Boundary

Create or maintain a dedicated native client workspace that consumes the existing STOA backend APIs and Cognito user pool. The backend remains the source of truth for identity, entitlements, quota, billing state, reports, notifications, and provider health.

The native app should reuse API contracts and product vocabulary from the web app where possible, but it should not attempt a literal web UI port. Mobile implementation should optimize the core journeys and share business contracts, not DOM assumptions.

## Suggested Module Layout

- `app/`: Expo Router route tree, role gates, deep-link entry points, and modal flows.
- `src/features/auth`: sign-in, registration, verification, resend-code, session restore, and sign-out.
- `src/features/student`: dashboard, curriculum/practice, question submission, quota state, teacher help, notifications, and history summary.
- `src/features/parent`: dashboard, child summary, child history, child report, account operations, and billing state.
- `src/services/api`: authenticated HTTP client, request IDs, API error mapping, and no-demo-fallback enforcement.
- `src/services/auth`: Amplify configuration, `fetchAuthSession` wrapper, refresh, and account-state derivation.
- `src/services/notifications`: permission handling, push token registration/revocation, notification response handling, and deep-link routing.
- `src/services/offline-cache`: persisted query cache, SQLite cache helpers, TTL/staleness policy, sign-out clearing, and privacy guards.
- `src/i18n`: resource loading, language selection, and mobile text-fit test fixtures.

## Auth And Session Flow

1. Configure Amplify with existing Cognito user pool and client identifiers.
2. On app start, restore the Amplify session and derive the user's role/account state from backend APIs.
3. Attach access tokens to API requests through a single API client wrapper.
4. Map backend auth, verification, entitlement, child-binding, provider, and quota errors into explicit mobile states.
5. Clear persisted query data, SecureStore metadata, and push-token registration on sign-out where possible.

## Push And Deep-Link Flow

1. Ask for notification permission at a clear product moment, not during cold launch.
2. Resolve Expo project ID and native push token.
3. Register the token through `POST /notifications/push-tokens` with provider/device metadata.
4. On logout, app uninstall signal, or user opt-out, revoke through `DELETE /notifications/push-tokens/{token_reference}` when possible.
5. Handle foreground notification presentation and background response separately.
6. Route notification actions through authenticated deep links such as parent report, child history, practice, teacher help, or notification detail.
7. Keep backend notification metadata support-safe and validate route targets after auth.

## Offline/Read-Through Flow

1. Cache selected GET responses only after authenticated successful reads.
2. Apply TTL and stale labels per surface: dashboard summaries can be short-lived, reports/history can have longer read-through windows, quota and billing state should be refreshed aggressively.
3. Block offline mutations by default for quota-consuming and billing/account-operation flows.
4. On sign-out or user switch, clear cached data and registered device state.
5. Never cache raw generated report artifacts, prompt bodies, answer text, provider payloads, billing payloads, or Cognito token material.

## Backend Contract Reuse

- Notifications: `/notifications`, `/notifications/push-tokens`, read/archive endpoints, and admin delivery evidence.
- Parent: subscription/account operations, child summary, history, and report endpoints.
- Student/practice: curriculum catalog/progress, lessons, challenges, hints, teacher help, and question submission.
- Quota/usage: use backend error codes and usage state rather than mobile-side quota guesses.

## Build Order

1. Native stack, workspace, app shell, navigation, and environment contract.
2. Auth/session restore, verification, account-state mapping, and secure storage policy.
3. Student and parent core mobile journeys against real backend APIs.
4. Push registration, notification handling, deep links, and offline/read-through cache.
5. Localization QA, release evidence, internal build, screenshots, and known blocker documentation.
