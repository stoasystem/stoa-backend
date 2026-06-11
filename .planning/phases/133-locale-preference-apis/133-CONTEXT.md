# Phase 133: Locale Preference APIs - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning
**Mode:** Autonomous single-pass discuss

<domain>
## Phase Boundary

Phase 133 implements durable locale preference support. It must expose effective locale on authenticated profile responses, persist supported locale updates, define deterministic fallback behavior, and remain compatible with existing clients.
</domain>

<decisions>
## Implementation Decisions

1. Reuse the existing `/auth/me` profile surface because it already returns `preferredLanguage`.
2. Add `preferredLocale` and `effectiveLocale` while keeping `preferredLanguage` for frontend compatibility.
3. Add `PATCH /auth/me/preferences/locale` as the authenticated durable update route.
4. Introduce a shared `locale_service` with supported locales `de` and `en`, default `de`, and region-tag normalization to the supported base locale.
5. Reject unsupported or malformed update inputs instead of storing unknown locale values.
6. Store locale on the existing user profile item and keep legacy `language` / `preferredLanguage` compatibility.
</decisions>

<code_context>
## Existing Code Insights

- `auth.py` already stores registration `preferredLanguage` into the profile `language` field.
- `UserOut` already exposes `preferredLanguage`.
- `user_repo.py` owns profile persistence and can add a narrow update helper.
- Existing auth tests use direct monkeypatching and FastAPI dependency overrides, so focused tests can validate behavior without live Cognito/DynamoDB.
</code_context>

<specifics>
## Specific Ideas

- Add `src/stoa/services/locale_service.py`.
- Add `user_repo.update_locale_preference`.
- Refactor `/auth/me` profile resolution into a helper that can also support the PATCH route.
- Add focused tests in `tests/test_locale_preferences.py`.
</specifics>

<deferred>
## Deferred Ideas

- `Accept-Language` negotiation.
- Full translation management.
- Locale metadata on non-auth role routes, which belongs to Phase 134.
</deferred>
