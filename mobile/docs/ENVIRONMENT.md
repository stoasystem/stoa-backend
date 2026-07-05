# STOA Mobile Environment Contract

## Required Values

- `EXPO_PUBLIC_STOA_API_BASE_URL`
- `EXPO_PUBLIC_STOA_COGNITO_REGION`
- `EXPO_PUBLIC_STOA_COGNITO_USER_POOL_ID`
- `EXPO_PUBLIC_STOA_COGNITO_CLIENT_ID`

## Push/Release Values

- `EXPO_PUBLIC_STOA_EXPO_PROJECT_ID`
- `EXPO_PUBLIC_STOA_RELEASE_CHANNEL`
- `EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK`

## Policy

- Access tokens are acquired through Amplify session APIs, not localStorage.
- Push registration must use backend notification endpoints.
- Offline cache must be read-through only until a quota-safe mutation design is approved.
- Sensitive content, provider payloads, billing payloads, and Cognito token material are not cached.
