# v5.19 Research Summary: Native Mobile Push And Offline Client Implementation

## Recommendation

Use Expo SDK 57, React Native 0.86, React 19.2, TypeScript, Expo Router, AWS Amplify Auth, Expo Notifications, Expo SecureStore, TanStack Query, and bounded SQLite/query persistence. Treat EAS internal builds as the v5.19 release evidence target.

## Feature Table Stakes

- Native app shell, environment contract, and role-aware navigation.
- Cognito-compatible auth/session restore, email verification, account-state mapping, secure storage policy, and sign-out clearing.
- Student core journeys for dashboard, curriculum/practice, question submission, quota state, teacher help, notifications, and history summary.
- Parent core journeys for dashboard, child summary/history/report, account operations, billing state, and support-safe explanations.
- Push token registration/revocation, notification list/read/archive, foreground/background handling, and authenticated deep links.
- Offline/read-through cache for selected read-only summaries with explicit TTL, stale-state UI, privacy limits, and cache clearing.
- Localization, text-fit/accessibility checks, internal build evidence, screenshots, tests, and provider/app-store blockers.

## Suggested Roadmap Shape

- Phase 267: Native Mobile Stack And App Shell Contract.
- Phase 268: Auth Session And Account State.
- Phase 269: Student And Parent Core Mobile Journeys.
- Phase 270: Native Push Deep Links And Offline Read-Through.
- Phase 271: Native Mobile Release Gate.

## Key Decisions

- Native storage must not repeat the web localStorage token pattern.
- Push should reuse backend notification contracts.
- Offline behavior should be read-through only by default.
- v5.19 should prove internal native readiness, not promise public app-store launch.

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
