# STOA Mobile Auth Contract

## Policy

- Use Amplify Auth for Cognito-compatible sign-in, sign-up, verification, resend-code, session restore, refresh-sensitive token access, and sign-out.
- Do not persist raw access tokens, ID tokens, refresh tokens, Cognito token material, or provider payloads in localStorage, AsyncStorage, SQLite, SecureStore, logs, or support evidence.
- SecureStore is allowed only for small session-adjacent metadata such as the last signed-in email or role hint.
- API requests attach access tokens from `fetchAuthSession()` through a single client wrapper.
- Sign-out clears query/offline cache, SecureStore metadata, and push token registration when the revoke hook is available.

## Account States

Mobile screens must distinguish these support-safe states:

- `verification_required`
- `session_expired`
- `entitlement_required`
- `billing_action_required`
- `child_binding_required`
- `quota_exhausted`
- `provider_blocked`
- `unauthorized`
- `forbidden`
- `unknown`

Generic `Forbidden` or `Unauthorized` copy is only a fallback when the backend does not provide a more specific support-safe code.
