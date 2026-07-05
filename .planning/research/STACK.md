# v5.19 Research: Native Mobile Stack

## Scope

v5.19 moves STOA from web/PWA readiness into a real native mobile client path. The client should cover authenticated student and parent journeys, native push registration, notification deep links, bounded offline/read-through behavior, localization QA, and release evidence while preserving the backend's no-demo-fallback rule.

## Current STOA Context

- Backend already exposes Cognito-compatible authenticated APIs for notifications, parents, practice, question submission, quota, account operations, and support-safe state.
- Adjacent frontend uses React 19, Vite, TypeScript, React Router 7, TanStack Query 5, Zustand, `aws-amplify`, and i18next.
- Existing web auth relies on `fetchAuthSession()` for access tokens, but the web store also persists `stoa_access_token` in localStorage. Native must not carry that storage pattern forward.
- Backend notification routes already include push token register/revoke, notification list, read/archive actions, and admin delivery status.

## Recommended Stack

- Mobile runtime: Expo SDK 57 with React Native 0.86, React 19.2, TypeScript, and Node 22.13.x.
- Navigation: Expo Router for file-based routes, deep links, and native navigation.
- Build/distribution: EAS Build internal distribution for device smoke and release evidence before any app-store launch.
- Auth: AWS Amplify Auth for Cognito compatibility and session refresh, matching the existing web integration.
- Secure storage: Expo SecureStore only for small native secrets/session-adjacent metadata when required. Do not persist raw access tokens in web-style localStorage.
- Server state: TanStack Query for API reads and mutation state, with a bounded persisted/read-through cache for offline-friendly screens.
- Local persistence: Expo SQLite for structured cached summaries where query persistence is not enough; avoid storing raw learning content or report artifacts.
- Push: Expo Notifications first, registering provider token references through existing backend push-token APIs. Direct FCM/APNs can remain a later provider path unless credentials and release goals require it now.
- Localization: Reuse the existing i18next resource model and add mobile text-fit/accessibility checks for English and Chinese strings.

## Version Evidence

- React Native's current stable release is 0.86.
- Expo SDK 57 maps to React Native 0.86, React 19.2.3, React Native Web 0.21.0, and Node 22.13.x.
- Expo SDK 57 targets Android 7+ and iOS 16.4+.
- Expo Notifications requires runtime permissions and a push token; Android production push requires FCM credentials and iOS requires Apple/APNs credentials.
- EAS Build can produce internal distribution binaries and manage signing credentials, which is the right release evidence target for this milestone.

## Implications For STOA

- v5.19 should not try to launch in app stores by default. It should produce a native implementation path, internal builds, screenshots, test output, and explicit provider/app-store blockers.
- Auth/session work is a first-class requirement because native storage, refresh, sign-out, verification, and provider-failure handling differ from web.
- Offline scope should be read-through and privacy-bounded. Offline mutation for questions, quota-consuming actions, billing, or account operations risks ledger drift and should stay out of scope unless explicitly approved.
- Push should reuse backend notification contracts instead of introducing a separate mobile-only notification model.

## Sources

- React Native versions: https://reactnative.dev/versions
- Expo SDK 57 reference: https://docs.expo.dev/versions/latest/
- Expo Router introduction: https://docs.expo.dev/router/introduction/
- EAS Build introduction: https://docs.expo.dev/build/introduction/
- Expo push notification setup: https://docs.expo.dev/push-notifications/push-notifications-setup/
- Expo SecureStore: https://docs.expo.dev/versions/latest/sdk/securestore/
- Expo SQLite: https://docs.expo.dev/versions/latest/sdk/sqlite/
- AWS Amplify React Native Auth: https://docs.amplify.aws/react-native/frontend/auth/
- TanStack Query network mode: https://tanstack.com/query/latest/docs/framework/react/guides/network-mode
- TanStack Query persistQueryClient: https://tanstack.com/query/latest/docs/framework/react/plugins/persistQueryClient
