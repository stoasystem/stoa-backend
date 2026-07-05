# STOA Mobile Stack Contract

## Runtime

- Expo SDK 57
- React Native 0.86
- React 19.2
- TypeScript 5.9
- Expo Router 7
- AWS Amplify 6 with React Native support
- TanStack Query 5
- Expo Notifications
- Expo SecureStore
- Expo SQLite

## Release Target

v5.19 targets internal native readiness evidence. Public App Store or Play Store launch is out of scope until a separate release approval covers store assets, privacy labels, native credentials, production push credentials, and review process.

## No Demo Fallback

The mobile client must not ship hidden demo data for authenticated routes. `EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK` defaults to enabled and release builds must keep it enabled.

## Local Limitation

Dependencies are declared but not installed by this phase. Local verification uses static contract tests until a mobile dependency install/build step is explicitly run.
