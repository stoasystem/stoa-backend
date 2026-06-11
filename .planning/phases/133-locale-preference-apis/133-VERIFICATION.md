# Phase 133 Verification

**Phase:** 133
**Verified:** 2026-06-11
**Status:** Passed

## Checks

| Check | Result | Notes |
|-------|--------|-------|
| Focused locale/auth tests | Passed | `.venv/bin/python -m pytest tests/test_locale_preferences.py tests/test_auth_account_lifecycle.py` -> 13 passed. |
| Focused ruff | Passed | `.venv/bin/python -m ruff check src/stoa/services/locale_service.py src/stoa/routers/auth.py src/stoa/db/repositories/user_repo.py tests/test_locale_preferences.py`. |
| Compatibility scan | Passed | No other direct `UserOut(...)` construction beyond updated auth refresh path. |

## Acceptance Criteria Evidence

1. `/auth/me` now exposes `preferredLocale` and `effectiveLocale` while preserving `preferredLanguage`.
2. `PATCH /auth/me/preferences/locale` persists supported locale updates through `user_repo.update_locale_preference`.
3. `locale_service` normalizes supported base/regional tags and rejects unsupported/malformed values.
4. Existing auth account lifecycle tests continue to pass.
