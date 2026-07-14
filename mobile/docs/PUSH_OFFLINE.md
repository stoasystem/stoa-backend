# STOA Mobile Push And Offline Contract

## Push

- Notification permission is requested at an intentional product moment.
- Expo push tokens are registered through `POST /notifications/push-tokens`.
- Push token revocation uses `DELETE /notifications/push-tokens/{token_reference}`.
- Foreground handling can show banner/list but must avoid leaking sensitive provider payloads.
- Notification payload route targets are treated as hints, not authorization.
- Deep links are validated after sign-in, account readiness, role checks, and route mapping.

## Offline Read-Through

- Offline cache is limited to approved read-only summaries.
- Question submission, teacher help, billing, subscription requests, and challenge answers are online-only.
- Cache entries must clear on sign-out and user switch.
- Stale data must be labeled.

## Forbidden Cache Categories

- raw prompts
- raw answers
- teaching transcripts
- generated report artifacts
- provider payloads
- billing payloads
- Cognito token material
- secrets
- private object keys

## Live Blockers

- Physical-device smoke requires Expo/EAS configuration and platform push credentials.
- Android production push requires FCM credentials.
- iOS production push requires Apple developer/APNs credentials.
